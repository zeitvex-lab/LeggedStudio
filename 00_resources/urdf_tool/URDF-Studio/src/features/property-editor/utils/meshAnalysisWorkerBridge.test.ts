import test from 'node:test';
import assert from 'node:assert/strict';

import {
  analyzeMeshBatchWithWorker,
  createMeshAnalysisWorkerClient,
} from './meshAnalysisWorkerBridge.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: unknown[] = [];

  public terminated = false;

  addEventListener(type: string, handler: WorkerEventHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerEventHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown): void {
    this.postedMessages.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  emitMessage(message: unknown): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }

  emitError(error: Error): void {
    this.listeners.get('error')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }

  emitMessageError(error: Error): void {
    this.listeners.get('messageerror')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }
}

test('analyzeMeshBatchWithWorker rejects instead of silently falling back to main-thread analysis', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    await assert.rejects(
      analyzeMeshBatchWithWorker({
        assets: {},
        tasks: [
          {
            targetId: 'mesh-target',
            cacheKey: 'mesh-target',
            meshPath: 'meshes/demo.stl',
          },
        ],
      }),
      /Web Worker is not available in this environment/i,
    );
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
  }
});

test('mesh analysis worker client spreads batches across pool workers and merges results', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 2,
  });

  const resultPromise = client.analyzeBatch({
    assets: {
      'meshes/a.stl': 'blob:a',
      'meshes/b.stl': 'blob:b',
      'meshes/c.stl': 'blob:c',
      'meshes/d.stl': 'blob:d',
    },
    tasks: [
      { targetId: 'a', cacheKey: 'mesh-a', meshPath: 'meshes/a.stl' },
      { targetId: 'b', cacheKey: 'mesh-b', meshPath: 'meshes/b.stl' },
      { targetId: 'c', cacheKey: 'mesh-c', meshPath: 'meshes/c.stl' },
      { targetId: 'd', cacheKey: 'mesh-d', meshPath: 'meshes/d.stl' },
    ],
  });

  assert.equal(workers.length, 2);
  assert.equal(workers[0]?.postedMessages.length, 1);
  assert.equal(workers[1]?.postedMessages.length, 1);

  workers.forEach((worker) => {
    const message = worker.postedMessages[0] as {
      requestId: number;
      tasks: Array<{ targetId: string; cacheKey: string }>;
    };

    worker.emitMessage({
      type: 'batch-result',
      requestId: message.requestId,
      results: message.tasks.map((task) => ({
        targetId: task.targetId,
        cacheKey: task.cacheKey,
        analysis: null,
      })),
    });
  });

  const results = await resultPromise;

  assert.deepEqual(results, {
    a: null,
    b: null,
    c: null,
    d: null,
  });
});

test('mesh analysis worker client keeps duplicate cache keys on the same worker chunk', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 2,
  });

  const resultPromise = client.analyzeBatch({
    assets: {
      'meshes/shared.stl': 'blob:shared',
      'meshes/other.stl': 'blob:other',
    },
    tasks: [
      { targetId: 'shared-a', cacheKey: 'shared', meshPath: 'meshes/shared.stl' },
      { targetId: 'shared-b', cacheKey: 'shared', meshPath: 'meshes/shared.stl' },
      { targetId: 'other', cacheKey: 'other', meshPath: 'meshes/other.stl' },
    ],
  });

  assert.equal(workers.length, 2);

  const postedTaskIds = workers.map((worker) => {
    const message = worker.postedMessages[0] as {
      requestId: number;
      tasks: Array<{ targetId: string }>;
    };
    return message.tasks.map((task) => task.targetId).sort();
  });

  assert(
    postedTaskIds.some((taskIds) => taskIds.includes('shared-a') && taskIds.includes('shared-b')),
  );

  workers.forEach((worker) => {
    const message = worker.postedMessages[0] as {
      requestId: number;
      tasks: Array<{ targetId: string; cacheKey: string }>;
    };

    worker.emitMessage({
      type: 'batch-result',
      requestId: message.requestId,
      results: message.tasks.map((task) => ({
        targetId: task.targetId,
        cacheKey: task.cacheKey,
        analysis: null,
      })),
    });
  });

  const results = await resultPromise;
  assert.deepEqual(results, {
    'shared-a': null,
    'shared-b': null,
    other: null,
  });
});

test('mesh analysis worker client rejects pending requests and recovers after worker errors', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 1,
  });

  const resultPromise = client.analyzeBatch({
    assets: {
      'meshes/demo.stl': 'blob:demo',
    },
    tasks: [
      {
        targetId: 'mesh-target',
        cacheKey: 'mesh-target',
        meshPath: 'meshes/demo.stl',
      },
    ],
  });

  assert.equal(workers[0]!.postedMessages.length, 1);
  workers[0]!.emitError(new Error('mesh analysis worker exploded'));

  await assert.rejects(resultPromise, /mesh analysis worker exploded/i);
  assert.equal(workers[0]!.terminated, true);

  const retryPromise = client.analyzeBatch({
    assets: {
      'meshes/retry.stl': 'blob:retry',
    },
    tasks: [
      {
        targetId: 'retry-target',
        cacheKey: 'retry-target',
        meshPath: 'meshes/retry.stl',
      },
    ],
  });

  assert.equal(workers.length, 2);
  const retryRequest = workers[1]!.postedMessages[0] as {
    requestId: number;
    tasks: Array<{ targetId: string; cacheKey: string }>;
  };
  workers[1]!.emitMessage({
    type: 'batch-result',
    requestId: retryRequest.requestId,
    results: retryRequest.tasks.map((task) => ({
      targetId: task.targetId,
      cacheKey: task.cacheKey,
      analysis: null,
    })),
  });

  assert.deepEqual(await retryPromise, {
    'retry-target': null,
  });
});

test('mesh analysis worker client rejects timed-out requests and recovers with a fresh worker', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 1,
    requestTimeoutMs: 10,
  });

  await assert.rejects(
    client.analyzeBatch({
      assets: {
        'meshes/demo.stl': 'blob:demo',
      },
      tasks: [
        {
          targetId: 'mesh-target',
          cacheKey: 'mesh-target',
          meshPath: 'meshes/demo.stl',
        },
      ],
    }),
    /did not respond within 10 ms/i,
  );
  assert.equal(workers[0]!.terminated, true);

  const retryPromise = client.analyzeBatch({
    assets: {
      'meshes/retry.stl': 'blob:retry',
    },
    tasks: [
      {
        targetId: 'retry-target',
        cacheKey: 'retry-target',
        meshPath: 'meshes/retry.stl',
      },
    ],
  });

  assert.equal(workers.length, 2);
  const retryRequest = workers[1]!.postedMessages[0] as {
    requestId: number;
    tasks: Array<{ targetId: string; cacheKey: string }>;
  };
  workers[1]!.emitMessage({
    type: 'batch-result',
    requestId: retryRequest.requestId,
    results: retryRequest.tasks.map((task) => ({
      targetId: task.targetId,
      cacheKey: task.cacheKey,
      analysis: null,
    })),
  });

  assert.deepEqual(await retryPromise, {
    'retry-target': null,
  });
});

test('mesh analysis worker client rejects pending requests when message transfer fails', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 1,
  });

  const resultPromise = client.analyzeBatch({
    assets: {
      'meshes/demo.stl': 'blob:demo',
    },
    tasks: [
      {
        targetId: 'mesh-target',
        cacheKey: 'mesh-target',
        meshPath: 'meshes/demo.stl',
      },
    ],
  });

  workers[0]!.emitMessageError(new Error('structured clone failed'));

  await assert.rejects(resultPromise, /message transfer failed/i);
  assert.equal(workers[0]!.terminated, true);
});

test('mesh analysis worker client terminates active worker requests when aborted', async () => {
  const workers: FakeWorker[] = [];
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 1,
  });
  const abortController = new AbortController();

  const resultPromise = client.analyzeBatch({
    assets: {
      'meshes/demo.stl': 'blob:demo',
    },
    tasks: [
      {
        targetId: 'mesh-target',
        cacheKey: 'mesh-target',
        meshPath: 'meshes/demo.stl',
      },
    ],
    signal: abortController.signal,
  });

  assert.equal(workers[0]!.postedMessages.length, 1);
  abortController.abort();

  await assert.rejects(resultPromise, /Mesh analysis aborted/i);
  assert.equal(workers[0]!.terminated, true);

  const retryPromise = client.analyzeBatch({
    assets: {
      'meshes/retry.stl': 'blob:retry',
    },
    tasks: [
      {
        targetId: 'retry-target',
        cacheKey: 'retry-target',
        meshPath: 'meshes/retry.stl',
      },
    ],
  });

  assert.equal(workers.length, 2);
  const retryRequest = workers[1]!.postedMessages[0] as {
    requestId: number;
    tasks: Array<{ targetId: string; cacheKey: string }>;
  };
  workers[1]!.emitMessage({
    type: 'batch-result',
    requestId: retryRequest.requestId,
    results: retryRequest.tasks.map((task) => ({
      targetId: task.targetId,
      cacheKey: task.cacheKey,
      analysis: null,
    })),
  });

  assert.deepEqual(await retryPromise, {
    'retry-target': null,
  });
});

test('mesh analysis worker client disposes partial pools after worker creation failures', async () => {
  const workers: FakeWorker[] = [];
  let createWorkerCalls = 0;
  const client = createMeshAnalysisWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      createWorkerCalls += 1;
      if (createWorkerCalls === 2) {
        throw new Error('mesh worker startup failed');
      }
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 2,
  });

  await assert.rejects(
    client.analyzeBatch({
      assets: {
        'meshes/a.stl': 'blob:a',
        'meshes/b.stl': 'blob:b',
      },
      tasks: [
        { targetId: 'a', cacheKey: 'mesh-a', meshPath: 'meshes/a.stl' },
        { targetId: 'b', cacheKey: 'mesh-b', meshPath: 'meshes/b.stl' },
      ],
    }),
    /mesh worker startup failed/i,
  );
  assert.equal(workers[0]!.terminated, true);

  const retryPromise = client.analyzeBatch({
    assets: {
      'meshes/retry.stl': 'blob:retry',
    },
    tasks: [
      {
        targetId: 'retry-target',
        cacheKey: 'retry-target',
        meshPath: 'meshes/retry.stl',
      },
    ],
  });

  assert.equal(workers.length, 2);
  const retryRequest = workers[1]!.postedMessages[0] as {
    requestId: number;
    tasks: Array<{ targetId: string; cacheKey: string }>;
  };
  workers[1]!.emitMessage({
    type: 'batch-result',
    requestId: retryRequest.requestId,
    results: retryRequest.tasks.map((task) => ({
      targetId: task.targetId,
      cacheKey: task.cacheKey,
      analysis: null,
    })),
  });

  assert.deepEqual(await retryPromise, {
    'retry-target': null,
  });
});

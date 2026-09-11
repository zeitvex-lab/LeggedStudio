import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createWorkerPoolClient,
  resolveDefaultWorkerCount,
  type WorkerLike,
} from './workerPoolClient.ts';

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

  emitMessage(data: unknown): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data });
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

test('createWorkerPoolClient grows workers lazily under concurrent pressure', async () => {
  const workers: FakeWorker[] = [];
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Lazy pool',
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as WorkerLike;
    },
    poolSize: 3,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  assert.equal(workers.length, 0);
  const first = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 1);
  const second = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 2);
  const third = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 3);
  const fourth = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 3);

  workers.forEach((worker, index) => {
    worker.postedMessages.forEach((message) => {
      const requestId = (message as { requestId: number }).requestId;
      worker.emitMessage({
        type: 'ok',
        requestId,
        result: `worker-${index}`,
      });
    });
  });

  assert.deepEqual(await Promise.all([first, second, third, fourth]), [
    'worker-0',
    'worker-1',
    'worker-2',
    'worker-0',
  ]);
});

test('resolveDefaultWorkerCount leaves one logical core for the main thread', () => {
  const originalNavigator = globalThis.navigator;

  try {
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: { hardwareConcurrency: 8 },
    });
    assert.equal(resolveDefaultWorkerCount(), 7);

    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: { hardwareConcurrency: 64 },
    });
    assert.equal(resolveDefaultWorkerCount(), 10);
  } finally {
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: originalNavigator,
    });
  }
});

test('createWorkerPoolClient rejects pending requests when disposed without a reason', async () => {
  const worker = new FakeWorker();
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Disposable pool',
    canUseWorker: () => true,
    createWorker: () => worker as unknown as WorkerLike,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  const pending = client.dispatch({ type: 'work' });
  assert.equal(client.pendingCount, 1);

  client.dispose();

  assert.equal(client.pendingCount, 0);
  assert.equal(worker.terminated, true);
  await assert.rejects(pending, /Disposable pool worker disposed/i);
});

test('createWorkerPoolClient rejects timed-out requests and tears down the stuck worker', async () => {
  const worker = new FakeWorker();
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Timeout pool',
    canUseWorker: () => true,
    createWorker: () => worker as unknown as WorkerLike,
    requestTimeoutMs: 10,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  await assert.rejects(
    client.dispatch({ type: 'work' }),
    /did not respond within 10 ms/i,
  );

  assert.equal(client.pendingCount, 0);
  assert.equal(client.workerCount, 0);
  assert.equal(worker.terminated, true);
});

test('createWorkerPoolClient creates a fresh worker after request timeout', async () => {
  const workers: FakeWorker[] = [];
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Recoverable timeout pool',
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as WorkerLike;
    },
    requestTimeoutMs: 10,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  await assert.rejects(client.dispatch({ type: 'work' }), /did not respond within 10 ms/i);
  assert.equal(workers.length, 1);
  assert.equal(workers[0].terminated, true);

  const second = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 2);
  const secondRequest = workers[1].postedMessages[0] as { requestId: number };
  workers[1].emitMessage({
    type: 'ok',
    requestId: secondRequest.requestId,
    result: 'fresh',
  });

  assert.equal(await second, 'fresh');
});

test('createWorkerPoolClient rejects pending requests when worker message transfer fails', async () => {
  const worker = new FakeWorker();
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Message error pool',
    canUseWorker: () => true,
    createWorker: () => worker as unknown as WorkerLike,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  const pending = client.dispatch({ type: 'work' });
  assert.equal(client.pendingCount, 1);

  worker.emitMessageError(new Error('structured clone failed'));

  await assert.rejects(pending, /message transfer failed/i);
  assert.equal(client.pendingCount, 0);
  assert.equal(client.workerCount, 0);
  assert.equal(worker.terminated, true);
});

test('createWorkerPoolClient rejects when response hydration throws after clearing pending state', async () => {
  const worker = new FakeWorker();
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Hydration failure pool',
    canUseWorker: () => true,
    createWorker: () => worker as unknown as WorkerLike,
    requestTimeoutMs: 10,
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: () => {
      throw new Error('hydrate failed');
    },
  });

  const pending = client.dispatch({ type: 'work' });
  const request = worker.postedMessages[0] as { requestId: number };
  worker.emitMessage({
    type: 'ok',
    requestId: request.requestId,
    result: 'ignored',
  });

  await assert.rejects(pending, /hydrate failed/i);
  assert.equal(client.pendingCount, 0);
});

test('createWorkerPoolClient creates a fresh worker after worker message transfer fails', async () => {
  const workers: FakeWorker[] = [];
  const client = createWorkerPoolClient<
    { requestId: number; type: 'ok'; result: string },
    string
  >({
    label: 'Recoverable message error pool',
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as WorkerLike;
    },
    getRequestId: (response) => response.requestId,
    isError: () => false,
    getError: () => '',
    getResult: (response) => response.result,
  });

  await assert.rejects(
    (async () => {
      const first = client.dispatch({ type: 'work' });
      workers[0].emitMessageError(new Error('structured clone failed'));
      await first;
    })(),
    /message transfer failed/i,
  );

  const second = client.dispatch({ type: 'work' });
  assert.equal(workers.length, 2);
  const secondRequest = workers[1].postedMessages[0] as { requestId: number };
  workers[1].emitMessage({
    type: 'ok',
    requestId: secondRequest.requestId,
    result: 'fresh',
  });

  assert.equal(await second, 'fresh');
});

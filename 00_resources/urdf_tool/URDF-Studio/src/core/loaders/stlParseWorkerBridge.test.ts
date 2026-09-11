import test from 'node:test';
import assert from 'node:assert/strict';

import { createStlParseWorkerPoolClient } from './stlParseWorkerBridge.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: unknown[] = [];

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

  terminate(): void {}

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
}

test('STL parse worker failures reject instead of silently reparsing on the main thread', async () => {
  const originalFetch = globalThis.fetch;
  const originalConsoleError = console.error;
  let fetchCount = 0;
  const fakeWorker = new FakeWorker();
  const consoleErrors: unknown[][] = [];

  globalThis.fetch = (async () => {
    fetchCount += 1;
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () => new ArrayBuffer(32),
    } as Response;
  }) as typeof fetch;
  console.error = (...args: unknown[]) => {
    consoleErrors.push(args);
  };

  try {
    const client = createStlParseWorkerPoolClient({
      canUseWorker: () => true,
      createWorker: () => fakeWorker as unknown as Worker,
      getWorkerCount: () => 1,
    });

    const resultPromise = client.load('/demo.stl');
    assert.equal(fakeWorker.postedMessages.length, 1);

    fakeWorker.emitError(new Error('stl worker exploded'));

    await assert.rejects(resultPromise, /stl worker exploded/i);
    // Subsequent loads for the same failed asset hit the bridge-level
    // failureCache and re-throw the original error without re-dispatching to
    // the (now-disabled) worker or falling back to inline fetch.
    await assert.rejects(client.load('/demo.stl'), /stl worker exploded/i);
    assert.equal(fetchCount, 0);
    assert.equal(consoleErrors.length, 1);
    assert.match(String(consoleErrors[0]?.[0] || ''), /STL parse worker crashed/i);
    assert.match(String(consoleErrors[0]?.[1] || ''), /stl worker exploded/i);
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalConsoleError;
  }
});

test('STL parse worker bridge parses inline when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;
  const originalFetch = globalThis.fetch;
  let fetchCount = 0;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });
  globalThis.fetch = (async () => {
    fetchCount += 1;
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      arrayBuffer: async () =>
        new TextEncoder().encode(
          [
            'solid triangle',
            'facet normal 0 0 1',
            'outer loop',
            'vertex 0 0 0',
            'vertex 1 0 0',
            'vertex 0 1 0',
            'endloop',
            'endfacet',
            'endsolid triangle',
          ].join('\n'),
        ).buffer,
    } as Response;
  }) as typeof fetch;

  try {
    const client = createStlParseWorkerPoolClient();
    const result = await client.load('/demo.stl');
    assert.equal(fetchCount, 1);
    assert.equal(new Float32Array(result.positions).length, 9);
    assert.equal(result.maxDimension, 1);
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    globalThis.fetch = originalFetch;
  }
});

test('STL parse worker cache can be cleared explicitly', async () => {
  const fakeWorker = new FakeWorker();
  const client = createStlParseWorkerPoolClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    getWorkerCount: () => 1,
  });

  const serializedResult = {
    positions: new Float32Array([0, 0, 0]).buffer,
    normals: new Float32Array([0, 0, 1]).buffer,
    maxDimension: 1,
  };

  const firstLoad = client.load('/demo.stl');
  assert.equal(fakeWorker.postedMessages.length, 1);
  fakeWorker.emitMessage({
    type: 'parse-stl-result',
    requestId: 1,
    result: serializedResult,
  });
  await assert.doesNotReject(firstLoad);

  await assert.doesNotReject(client.load('/demo.stl'));
  assert.equal(fakeWorker.postedMessages.length, 1);

  client.clearCache();

  const secondLoad = client.load('/demo.stl');
  assert.equal(fakeWorker.postedMessages.length, 2);
  fakeWorker.emitMessage({
    type: 'parse-stl-result',
    requestId: 2,
    result: serializedResult,
  });
  await assert.doesNotReject(secondLoad);
});

test('STL parse worker pool can be disposed and recreated on demand', async () => {
  const workers: FakeWorker[] = [];
  const client = createStlParseWorkerPoolClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker as unknown as Worker;
    },
    getWorkerCount: () => 1,
  });

  const serializedResult = {
    positions: new Float32Array([0, 0, 0]).buffer,
    normals: new Float32Array([0, 0, 1]).buffer,
    maxDimension: 1,
  };

  const firstLoad = client.load('/demo.stl');
  assert.equal(workers.length, 1);
  assert.equal(workers[0]?.postedMessages.length, 1);
  workers[0]?.emitMessage({
    type: 'parse-stl-result',
    requestId: 1,
    result: serializedResult,
  });
  await assert.doesNotReject(firstLoad);

  client.dispose();

  const secondLoad = client.load('/second.stl');
  assert.equal(workers.length, 2);
  assert.equal(workers[0]?.postedMessages.length, 1);
  assert.equal(workers[1]?.postedMessages.length, 1);
  workers[1]?.emitMessage({
    type: 'parse-stl-result',
    requestId: 2,
    result: serializedResult,
  });
  await assert.doesNotReject(secondLoad);
});

import test from 'node:test';
import assert from 'node:assert/strict';

import type { UsdBinaryArchiveWorkerResponse } from './usdBinaryArchiveWorker.ts';
import {
  createUsdBinaryArchiveWorkerClient,
} from './usdBinaryArchiveWorkerBridge.ts';
import {
  serializeUsdBinaryArchiveFilesForWorker,
} from './usdBinaryArchiveWorkerTransfer.ts';

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

  postMessage(message: unknown, _transfer?: Transferable[]): void {
    this.postedMessages.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  emitMessage(message: UsdBinaryArchiveWorkerResponse): void {
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

test('USD binary archive worker client resolves successful worker responses and forwards progress', async () => {
  const fakeWorker = new FakeWorker();
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });

  const progressEvents: string[] = [];
  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'], { type: 'text/plain;charset=utf-8' })],
  ]);

  const resultPromise = client.convert(archiveFiles, {
    onProgress: ({ filePath }) => progressEvents.push(filePath),
  });

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(fakeWorker.postedMessages.length, 1);
  const postedRequest = fakeWorker.postedMessages[0] as { requestId: number };
  const serialized = await serializeUsdBinaryArchiveFilesForWorker(new Map<string, Blob>([
    ['robot.usd', new Blob(['PXR-USDCROOT#usda 1.0\n'], { type: 'application/octet-stream' })],
  ]));

  fakeWorker.emitMessage({
    type: 'convert-usd-archive-files-to-binary-progress',
    requestId: postedRequest.requestId,
    current: 1,
    total: 1,
    filePath: 'robot.usd',
  });
  fakeWorker.emitMessage({
    type: 'convert-usd-archive-files-to-binary-result',
    requestId: postedRequest.requestId,
    result: serialized.payload,
  });

  const result = await resultPromise;
  assert.deepEqual(progressEvents, ['robot.usd']);
  assert.equal(await result.get('robot.usd')?.text(), 'PXR-USDCROOT#usda 1.0\n');
});

test('USD binary archive worker client rejects immediately when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    const client = createUsdBinaryArchiveWorkerClient();
    await assert.rejects(
      client.convert(new Map()),
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

test('USD binary archive worker client rejects with timeout and tears down when the worker goes silent (WASM crash)', async () => {
  const fakeWorker = new FakeWorker();
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    requestTimeoutMs: 10,
  });

  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'])],
  ]);

  // Worker never emits any message — simulates a WASM trap that killed the
  // thread without dispatching an error event. The watchdog must fire.
  await assert.rejects(
    client.convert(archiveFiles),
    /did not respond within the timeout/i,
  );

  // The dead worker must be terminated so the next attempt starts clean.
  assert.equal(fakeWorker.terminated, true);
});

test('USD binary archive worker client rejects when message transfer fails', async () => {
  const fakeWorker = new FakeWorker();
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    requestTimeoutMs: 0,
  });

  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'])],
  ]);
  const resultPromise = client.convert(archiveFiles);

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(fakeWorker.postedMessages.length, 1);

  fakeWorker.emitMessageError(new Error('structured clone failed'));

  await assert.rejects(resultPromise, /message transfer failed/i);
  assert.equal(fakeWorker.terminated, true);
});

test('USD binary archive worker client rebuilds a fresh worker after an error response instead of reusing the dead one', async () => {
  const createdWorkers: FakeWorker[] = [];
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      createdWorkers.push(worker);
      return worker as unknown as Worker;
    },
    // Disable the watchdog for this test so timing does not interfere.
    requestTimeoutMs: 0,
  });

  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'])],
  ]);

  // First request: worker reports a WASM-style conversion error.
  const firstPromise = client.convert(archiveFiles);
  for (let attempt = 0; attempt < 10 && createdWorkers.length < 1; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  for (let attempt = 0; attempt < 10 && createdWorkers[0].postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  const firstRequest = createdWorkers[0].postedMessages[0] as { requestId: number };
  createdWorkers[0].emitMessage({
    type: 'convert-usd-archive-files-to-binary-error',
    requestId: firstRequest.requestId,
    error: 'memory access out of bounds',
  });
  await assert.rejects(firstPromise, /memory access out of bounds/i);

  // Second request must spawn a NEW worker instance, not reuse the one that
  // reported the error. This is the regression guard for the "second click
  // freezes the UI" bug.
  assert.equal(createdWorkers[0].terminated, true);

  const secondPromise = client.convert(archiveFiles);
  for (let attempt = 0; attempt < 10 && createdWorkers.length < 2; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(createdWorkers.length, 2, 'second convert must create a fresh worker');
  assert.notEqual(createdWorkers[1], createdWorkers[0]);

  for (let attempt = 0; attempt < 10 && createdWorkers[1].postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  const secondRequest = createdWorkers[1].postedMessages[0] as { requestId: number };
  const serialized = await serializeUsdBinaryArchiveFilesForWorker(
    new Map<string, Blob>([
      ['robot.usd', new Blob(['PXR-USDCROOT#usda 1.0\n'], { type: 'application/octet-stream' })],
    ]),
  );
  createdWorkers[1].emitMessage({
    type: 'convert-usd-archive-files-to-binary-result',
    requestId: secondRequest.requestId,
    result: serialized.payload,
  });

  const secondResult = await secondPromise;
  assert.equal(await secondResult.get('robot.usd')?.text(), 'PXR-USDCROOT#usda 1.0\n');
});

test('USD binary archive worker client rejects sibling pending requests immediately when one request poisons the worker', async () => {
  const fakeWorker = new FakeWorker();
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    requestTimeoutMs: 0,
  });

  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'])],
  ]);
  const firstPromise = client.convert(archiveFiles);
  const secondPromise = client.convert(archiveFiles);

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length < 2; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(fakeWorker.postedMessages.length, 2);
  const firstRequest = fakeWorker.postedMessages[0] as { requestId: number };

  fakeWorker.emitMessage({
    type: 'convert-usd-archive-files-to-binary-error',
    requestId: firstRequest.requestId,
    error: 'memory access out of bounds',
  });

  await assert.rejects(firstPromise, /memory access out of bounds/i);
  await assert.rejects(secondPromise, /memory access out of bounds/i);
  assert.equal(fakeWorker.terminated, true);
});

test('USD binary archive worker client recovers after a worker error event', async () => {
  const createdWorkers: FakeWorker[] = [];
  const client = createUsdBinaryArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => {
      const worker = new FakeWorker();
      createdWorkers.push(worker);
      return worker as unknown as Worker;
    },
    requestTimeoutMs: 0,
  });

  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'])],
  ]);
  const firstPromise = client.convert(archiveFiles);

  for (let attempt = 0; attempt < 10 && createdWorkers.length < 1; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  createdWorkers[0].emitError(new Error('worker crashed'));
  await assert.rejects(firstPromise, /worker crashed/i);

  const secondPromise = client.convert(archiveFiles);
  for (let attempt = 0; attempt < 10 && createdWorkers.length < 2; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(createdWorkers.length, 2, 'retry after worker error must create a fresh worker');
  client.dispose(new Error('test cleanup'));
  await assert.rejects(secondPromise, /test cleanup/i);
});

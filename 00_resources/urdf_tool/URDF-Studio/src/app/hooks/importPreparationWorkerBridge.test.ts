import test from 'node:test';
import assert from 'node:assert/strict';

import {
  disposeImportPreparationWorker,
  prepareImportPayloadWithWorker,
} from './importPreparationWorkerBridge.ts';

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

  emitMessageError(error: Error): void {
    this.listeners.get('messageerror')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }
}

test('import preparation worker bridge rejects immediately when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    await assert.rejects(
      prepareImportPayloadWithWorker({
        files: [],
        existingPaths: [],
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

test('import preparation worker bridge rejects pending work when message transfer fails', async () => {
  const originalWorker = globalThis.Worker;
  const fakeWorkers: FakeWorker[] = [];
  const createFakeWorker = function ImportPreparationWorkerMock() {
    const worker = new FakeWorker();
    fakeWorkers.push(worker);
    return worker;
  };

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: createFakeWorker as unknown as typeof Worker,
  });

  try {
    const resultPromise = prepareImportPayloadWithWorker({
      files: [],
      existingPaths: [],
    });

    const fakeWorker = fakeWorkers[0];
    assert.ok(fakeWorker);
    assert.equal(fakeWorker.postedMessages.length, 1);
    fakeWorker.emitMessageError(new Error('structured clone failed'));

    await assert.rejects(resultPromise, /message transfer failed/i);
    assert.equal(fakeWorker.terminated, true);
  } finally {
    disposeImportPreparationWorker();
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
  }
});

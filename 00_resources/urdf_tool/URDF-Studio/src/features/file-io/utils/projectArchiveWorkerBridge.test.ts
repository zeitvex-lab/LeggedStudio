import test from 'node:test';
import assert from 'node:assert/strict';

import type { ProjectArchiveWorkerResponse } from './projectArchiveWorker.ts';
import {
  createProjectArchiveWorkerClient,
} from './projectArchiveWorkerBridge.ts';

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

  emitMessage(message: ProjectArchiveWorkerResponse): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }
}

test('project archive worker client resolves successful worker responses and forwards progress', async () => {
  const fakeWorker = new FakeWorker();
  const client = createProjectArchiveWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });

  const progressEvents: string[] = [];
  const resultPromise = client.build(new Map([
    ['README.md', '# archive'],
  ]), {
    onProgress: ({ label }) => progressEvents.push(label || ''),
  });

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(fakeWorker.postedMessages.length, 1);
  const postedRequest = fakeWorker.postedMessages[0] as { requestId: number };

  fakeWorker.emitMessage({
    type: 'build-project-archive-progress',
    requestId: postedRequest.requestId,
    completed: 42,
    total: 100,
    label: 'README.md',
  });
  fakeWorker.emitMessage({
    type: 'build-project-archive-result',
    requestId: postedRequest.requestId,
    result: {
      bytes: new TextEncoder().encode('PK').buffer,
      mimeType: 'application/zip',
    },
  });

  const result = await resultPromise;
  assert.deepEqual(progressEvents, ['README.md']);
  assert.equal(result.type, 'application/zip');
  assert.deepEqual(Array.from(new Uint8Array(await result.arrayBuffer())), [80, 75]);
});

test('project archive worker client rejects immediately when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    const client = createProjectArchiveWorkerClient();
    await assert.rejects(
      client.build(new Map()),
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

import test from 'node:test';
import assert from 'node:assert/strict';

import { createMshParseWorkerPoolClient } from './mshParseWorkerBridge.ts';

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
    this.listeners.get('message')?.forEach((handler) => handler({ data: message }));
  }
}

function createLegacyMshBuffer(): ArrayBuffer {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]);
  const indices = new Int32Array([0, 1, 2, 0, 1, 3, 0, 2, 3, 1, 2, 3]);
  const buffer = new ArrayBuffer(16 + positions.byteLength + indices.byteLength);
  const view = new DataView(buffer);
  view.setInt32(0, 4, true);
  view.setInt32(4, 0, true);
  view.setInt32(8, 0, true);
  view.setInt32(12, 4, true);
  new Float32Array(buffer, 16, positions.length).set(positions);
  new Int32Array(buffer, 16 + positions.byteLength, indices.length).set(indices);
  return buffer;
}

function createDataUrl(buffer: ArrayBuffer): string {
  return `data:application/octet-stream;base64,${Buffer.from(buffer).toString('base64')}`;
}

test('MSH parse worker bridge falls back to inline parsing when Worker is unavailable', async () => {
  const client = createMshParseWorkerPoolClient({
    canUseWorker: () => false,
  });

  const result = await client.load(createDataUrl(createLegacyMshBuffer()));

  assert.equal(new Float32Array(result.positions).length, 12);
  assert.equal(new Int32Array(result.indices ?? new ArrayBuffer(0)).length, 12);
});

test('MSH parse worker bridge resolves worker results and returns cloned cached buffers', async () => {
  const fakeWorker = new FakeWorker();
  const client = createMshParseWorkerPoolClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    getWorkerCount: () => 1,
  });

  const firstLoad = client.load('blob:msh');
  assert.equal(fakeWorker.postedMessages.length, 1);
  const message = fakeWorker.postedMessages[0] as { requestId: number };
  fakeWorker.emitMessage({
    type: 'parse-msh-result',
    requestId: message.requestId,
    result: {
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1]).buffer,
      normals: null,
      uvs: null,
      indices: new Int32Array([0, 1, 2, 0, 1, 3, 0, 2, 3, 1, 2, 3]).buffer,
      maxDimension: 1,
    },
  });

  const firstResult = await firstLoad;
  const secondResult = await client.load('blob:msh');

  assert.equal(fakeWorker.postedMessages.length, 1);
  assert.notEqual(secondResult.positions, firstResult.positions);
  assert.deepEqual([...new Float32Array(secondResult.positions).slice(0, 3)], [0, 0, 0]);
});

import test from 'node:test';
import assert from 'node:assert/strict';

import type { StlCompressionWorkerResponse } from './stlCompressionWorkerProtocol.ts';
import { createStlCompressionWorkerClient } from './stlCompressionWorkerBridge.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

interface PostedWorkerMessage {
  message: unknown;
  transfer?: Transferable[];
}

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: PostedWorkerMessage[] = [];

  public terminated = false;

  addEventListener(type: string, handler: WorkerEventHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerEventHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown, transfer?: Transferable[]): void {
    this.postedMessages.push({ message, transfer });
  }

  terminate(): void {
    this.terminated = true;
  }

  emitMessage(message: StlCompressionWorkerResponse): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }
}

function createAsciiStlBlob(): Blob {
  return new Blob([
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
  ]);
}

function createArrayBuffer(bytes: number[]): ArrayBuffer {
  const buffer = new ArrayBuffer(bytes.length);
  new Uint8Array(buffer).set(bytes);
  return buffer;
}

async function waitForPostedMessage(fakeWorker: FakeWorker): Promise<PostedWorkerMessage> {
  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  assert.equal(fakeWorker.postedMessages.length, 1);
  return fakeWorker.postedMessages[0]!;
}

test('STL compression worker bridge passes non-STL blobs through without dispatching', async () => {
  const fakeWorker = new FakeWorker();
  const client = createStlCompressionWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });
  const blob = new Blob(['v 0 0 0\n']);

  const result = await client.compress(blob, 'mesh.obj', { quality: 25 });

  assert.equal(result.blob, blob);
  assert.equal(result.originalTriangleCount, 0);
  assert.equal(result.compressionRatio, 0);
  assert.equal(fakeWorker.postedMessages.length, 0);
});

test('STL compression worker bridge resolves worker success responses and transfers buffers', async () => {
  const fakeWorker = new FakeWorker();
  const client = createStlCompressionWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });

  const resultPromise = client.compress(createAsciiStlBlob(), 'mesh.stl', { quality: 50 });
  const posted = await waitForPostedMessage(fakeWorker);
  const request = posted.message as {
    requestId: number;
    type: string;
    filename: string;
    sourceBuffer: ArrayBuffer;
    quality: number;
  };

  assert.equal(request.type, 'compress-stl');
  assert.equal(request.filename, 'mesh.stl');
  assert.equal(request.quality, 50);
  assert.equal(posted.transfer?.length, 1);
  assert.equal(posted.transfer?.[0], request.sourceBuffer);

  fakeWorker.emitMessage({
    type: 'compress-stl-result',
    requestId: request.requestId,
    result: {
      outputBuffer: createArrayBuffer([1, 2, 3, 4]),
      originalTriangleCount: 10,
      compressedTriangleCount: 4,
      originalSize: request.sourceBuffer.byteLength,
      compressedSize: 4,
      compressionRatio: 60,
    },
  });

  const result = await resultPromise;
  assert.equal(result.originalTriangleCount, 10);
  assert.equal(result.compressedTriangleCount, 4);
  assert.equal(result.compressedSize, 4);
  assert.equal(result.compressionRatio, 60);
  assert.deepEqual(Array.from(new Uint8Array(await result.blob.arrayBuffer())), [1, 2, 3, 4]);
});

test('STL compression worker bridge falls back inline when Worker is unavailable', async () => {
  const client = createStlCompressionWorkerClient({
    canUseWorker: () => false,
    createWorker: () => {
      throw new Error('worker should not be created');
    },
  });

  const result = await client.compress(createAsciiStlBlob(), 'mesh.stl', { quality: 100 });

  assert.equal(result.originalTriangleCount, 1);
  assert.equal(result.compressedTriangleCount, 1);
  assert.equal(result.compressedSize, 134);
  assert.equal(result.blob.size, 134);
});

test('STL compression worker bridge falls back inline after worker errors', async () => {
  const originalConsoleError = console.error;
  const consoleErrors: unknown[][] = [];
  const fakeWorker = new FakeWorker();
  const client = createStlCompressionWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });
  console.error = (...args: unknown[]) => {
    consoleErrors.push(args);
  };

  try {
    const resultPromise = client.compress(createAsciiStlBlob(), 'mesh.stl', { quality: 100 });
    const posted = await waitForPostedMessage(fakeWorker);
    const request = posted.message as { requestId: number };

    fakeWorker.emitMessage({
      type: 'compress-stl-error',
      requestId: request.requestId,
      error: 'worker compression failed',
    });

    const result = await resultPromise;
    assert.equal(result.originalTriangleCount, 1);
    assert.equal(result.compressedTriangleCount, 1);
    assert.equal(result.compressedSize, 134);
    assert.equal(consoleErrors.length, 1);
  } finally {
    console.error = originalConsoleError;
  }
});

test('STL compression worker bridge propagates worker errors when inline fallback is disabled', async () => {
  const originalConsoleError = console.error;
  const fakeWorker = new FakeWorker();
  const client = createStlCompressionWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    fallbackToInline: false,
  });
  console.error = () => {};

  try {
    const resultPromise = client.compress(createAsciiStlBlob(), 'mesh.stl', { quality: 100 });
    const posted = await waitForPostedMessage(fakeWorker);
    const request = posted.message as { requestId: number };

    fakeWorker.emitMessage({
      type: 'compress-stl-error',
      requestId: request.requestId,
      error: 'worker compression failed',
    });

    await assert.rejects(resultPromise, /worker compression failed/i);
  } finally {
    console.error = originalConsoleError;
  }
});

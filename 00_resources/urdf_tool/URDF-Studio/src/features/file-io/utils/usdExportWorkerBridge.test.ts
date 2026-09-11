import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotState } from '@/types';
import type { UsdExportWorkerResponse } from './usdExportWorker.ts';
import {
  createUsdExportWorkerClient,
} from './usdExportWorkerBridge.ts';
import {
  serializeUsdExportResultForWorker,
} from './usdExportWorkerTransfer.ts';

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

  emitMessage(message: UsdExportWorkerResponse): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }
}

const TEST_ROBOT: RobotState = {
  name: 'worker_bot',
  links: {},
  joints: {},
  rootLinkId: '',
  selection: { type: null, id: null },
};

test('usdExport worker client resolves successful worker responses and forwards progress', async () => {
  const fakeWorker = new FakeWorker();
  const client = createUsdExportWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });

  const progressEvents: string[] = [];
  const resultPromise = client.export({
    robot: TEST_ROBOT,
    exportName: 'worker_bot',
    assets: {},
    extraMeshFiles: new Map<string, Blob>([
      ['meshes/base.glb', new Blob(['mesh-bytes'], { type: 'model/gltf-binary' })],
    ]),
    onProgress: ({ phase }) => progressEvents.push(phase),
  });

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  assert.equal(fakeWorker.postedMessages.length, 1);
  const postedRequest = fakeWorker.postedMessages[0] as { requestId: number };

  const serialized = await serializeUsdExportResultForWorker({
    content: '#usda 1.0\n',
    downloadFileName: 'worker_bot.usd',
    archiveFileName: 'worker_bot_usd.zip',
    rootLayerPath: 'worker_bot/usd/worker_bot.usd',
    archiveFiles: new Map<string, Blob>([
      ['worker_bot/usd/worker_bot.usd', new Blob(['PXR-USDCROOT'], { type: 'application/octet-stream' })],
    ]),
  });

  fakeWorker.emitMessage({
    type: 'export-robot-to-usd-progress',
    requestId: postedRequest.requestId,
    progress: {
      phase: 'links',
      completed: 1,
      total: 1,
      label: 'base_link',
    },
  });
  fakeWorker.emitMessage({
    type: 'export-robot-to-usd-result',
    requestId: postedRequest.requestId,
    result: serialized.payload,
  });

  const result = await resultPromise;
  assert.deepEqual(progressEvents, ['links']);
  assert.equal(result.downloadFileName, 'worker_bot.usd');
  assert.equal(await result.archiveFiles.get('worker_bot/usd/worker_bot.usd')?.text(), 'PXR-USDCROOT');
});

test('usdExport worker client rejects immediately when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    const client = createUsdExportWorkerClient();
    await assert.rejects(
      client.export({
        robot: TEST_ROBOT,
        exportName: 'worker_bot',
        assets: {},
      }),
      /USD export worker is not available in this environment/i,
    );
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
  }
});

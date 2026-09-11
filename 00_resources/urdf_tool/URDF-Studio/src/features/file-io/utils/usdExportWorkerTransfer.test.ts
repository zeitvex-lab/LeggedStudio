import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotState } from '@/types';
import {
  hydrateUsdExportRequestFromWorker,
  hydrateUsdExportResultFromWorker,
  serializeUsdExportRequestForWorker,
  serializeUsdExportResultForWorker,
} from './usdExportWorkerTransfer.ts';

const TEST_ROBOT: RobotState = {
  name: 'worker_bot',
  links: {},
  joints: {},
  rootLinkId: '',
  selection: { type: null, id: null },
};

test('usdExport worker transfer serialization preserves extra mesh blobs in request payloads', async () => {
  const serialized = await serializeUsdExportRequestForWorker({
    robot: TEST_ROBOT,
    exportName: 'worker_bot',
    assets: {
      'meshes/base.glb': 'blob:mesh-base',
    },
    extraMeshFiles: new Map<string, Blob>([
      ['meshes/base.glb', new Blob(['mesh-bytes'], { type: 'model/gltf-binary' })],
      ['textures/base.png', new Blob([new Uint8Array([1, 2, 3])], { type: 'image/png' })],
    ]),
    meshCompression: {
      enabled: true,
      quality: 0.5,
    },
  });

  assert.equal(serialized.payload.exportName, 'worker_bot');
  assert.equal(serialized.payload.extraMeshFiles.length, 2);
  assert.equal(serialized.transferables.length, 0);
  assert.ok(serialized.payload.extraMeshFiles.every((file) => file.blob instanceof Blob));

  const hydrated = hydrateUsdExportRequestFromWorker(serialized.payload);
  assert.equal(hydrated.exportName, 'worker_bot');
  assert.equal(hydrated.assets['meshes/base.glb'], 'blob:mesh-base');
  assert.equal(await hydrated.extraMeshFiles?.get('meshes/base.glb')?.text(), 'mesh-bytes');
  const textureBlob = hydrated.extraMeshFiles?.get('textures/base.png');
  assert.ok(textureBlob);
  assert.deepEqual(Array.from(new Uint8Array(await textureBlob.arrayBuffer())), [1, 2, 3]);
  assert.deepEqual(hydrated.meshCompression, {
    enabled: true,
    quality: 0.5,
  });
});

test('usdExport worker transfer serialization preserves archive blobs in result payloads', async () => {
  const serialized = await serializeUsdExportResultForWorker({
    content: '#usda 1.0\n',
    downloadFileName: 'worker_bot.usd',
    archiveFileName: 'worker_bot_usd.zip',
    rootLayerPath: 'worker_bot/usd/worker_bot.usd',
    archiveFiles: new Map<string, Blob>([
      [
        'worker_bot/usd/worker_bot.usd',
        new Blob(['PXR-USDCROOT'], { type: 'application/octet-stream' }),
      ],
      ['worker_bot/assets/base.png', new Blob([new Uint8Array([9, 8, 7])], { type: 'image/png' })],
    ]),
  });

  assert.equal(serialized.payload.archiveFiles.length, 2);
  assert.equal(serialized.transferables.length, 0);
  assert.ok(serialized.payload.archiveFiles.every((file) => file.blob instanceof Blob));

  const hydrated = hydrateUsdExportResultFromWorker(serialized.payload);
  assert.equal(hydrated.downloadFileName, 'worker_bot.usd');
  assert.equal(hydrated.archiveFileName, 'worker_bot_usd.zip');
  assert.equal(hydrated.rootLayerPath, 'worker_bot/usd/worker_bot.usd');
  assert.equal(
    await hydrated.archiveFiles.get('worker_bot/usd/worker_bot.usd')?.text(),
    'PXR-USDCROOT',
  );
  assert.deepEqual(
    Array.from(
      new Uint8Array(await hydrated.archiveFiles.get('worker_bot/assets/base.png')!.arrayBuffer()),
    ),
    [9, 8, 7],
  );
});

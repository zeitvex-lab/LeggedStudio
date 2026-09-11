import test from 'node:test';
import assert from 'node:assert/strict';

import {
  hydrateUsdBinaryArchiveFilesFromWorker,
  serializeUsdBinaryArchiveFilesForWorker,
} from './usdBinaryArchiveWorkerTransfer.ts';

test('usdBinaryArchive transfer serialization preserves archive blobs across worker boundaries', async () => {
  const archiveFiles = new Map<string, Blob>([
    ['robot.usd', new Blob(['#usda 1.0\n'], { type: 'text/plain;charset=utf-8' })],
    ['textures/checker.png', new Blob([new Uint8Array([1, 2, 3])], { type: 'application/octet-stream' })],
  ]);

  const serialized = await serializeUsdBinaryArchiveFilesForWorker(archiveFiles);

  assert.equal(serialized.payload.files.length, 2);
  assert.equal(serialized.transferables.length, 2);
  assert.equal(serialized.payload.files[0]?.path, 'robot.usd');

  const hydrated = hydrateUsdBinaryArchiveFilesFromWorker(serialized.payload);

  assert.equal(await hydrated.get('robot.usd')?.text(), '#usda 1.0\n');
  assert.deepEqual(
    Array.from(new Uint8Array(await hydrated.get('textures/checker.png')!.arrayBuffer())),
    [1, 2, 3],
  );
});

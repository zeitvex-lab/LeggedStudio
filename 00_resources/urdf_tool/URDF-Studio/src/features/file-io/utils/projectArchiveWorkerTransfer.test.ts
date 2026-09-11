import test from 'node:test';
import assert from 'node:assert/strict';

import {
  hydrateProjectArchiveBlobFromWorker,
  hydrateProjectArchiveEntriesFromWorker,
  serializeProjectArchiveEntriesForWorker,
} from './projectArchiveWorkerTransfer.ts';

test('project archive worker transfer serializes mixed archive entries and hydrates worker payloads', async () => {
  const serialized = await serializeProjectArchiveEntriesForWorker(
    new Map<string, string | Uint8Array | Blob>([
      ['README.md', '# project archive'],
      ['assets/data.bin', new Uint8Array([1, 2, 3])],
      ['output/robot.usd', new Blob(['#usda 1.0\n'], { type: 'text/plain;charset=utf-8' })],
    ]),
  );

  assert.equal(serialized.payload.files.length, 3);
  assert.equal(serialized.transferables.length, 1);
  assert.deepEqual(
    serialized.payload.files.map((file) => file.kind),
    ['text', 'bytes', 'blob'],
  );

  const hydrated = hydrateProjectArchiveEntriesFromWorker(serialized.payload);
  assert.equal(hydrated.get('README.md'), '# project archive');
  assert.deepEqual(
    Array.from(new Uint8Array(hydrated.get('assets/data.bin') as ArrayBuffer)),
    [1, 2, 3],
  );
  assert.equal(await (hydrated.get('output/robot.usd') as Blob).text(), '#usda 1.0\n');

  const blob = hydrateProjectArchiveBlobFromWorker({
    bytes: new Uint8Array([80, 75, 3, 4]).buffer,
    mimeType: 'application/zip',
  });
  assert.equal(blob.type, 'application/zip');
  assert.deepEqual(Array.from(new Uint8Array(await blob.arrayBuffer())), [80, 75, 3, 4]);
});

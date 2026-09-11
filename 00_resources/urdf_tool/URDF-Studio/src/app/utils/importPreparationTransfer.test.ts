import test from 'node:test';
import assert from 'node:assert/strict';

import {
  hydratePreparedImportPayloadFromWorker,
  serializePreparedImportPayloadForWorker,
} from './importPreparationTransfer.ts';
import type { PreparedImportPayload } from './importPreparation.ts';

test('importPreparation transfer serialization preserves binary payloads across worker boundaries', async () => {
  const payload: PreparedImportPayload = {
    robotFiles: [
      {
        name: 'robot/demo.urdf',
        format: 'urdf',
        content: '<robot name="demo"><link name="base_link" /></robot>',
      },
    ],
    assetFiles: [
      {
        name: 'robot/meshes/base.stl',
        blob: new Blob(['solid demo'], { type: 'model/stl' }),
      },
    ],
    deferredAssetFiles: [],
    usdSourceFiles: [
      {
        name: 'robot/usd/demo.usdc',
        blob: new Blob([new Uint8Array([80, 88, 82, 45])], { type: 'application/octet-stream' }),
      },
    ],
    libraryFiles: [
      {
        path: 'robot/motor library/Acme/M1.txt',
        content: '{"name":"M1"}',
      },
    ],
    textFiles: [
      {
        path: 'robot/materials/demo.material',
        content: 'material Demo {}',
      },
    ],
    preferredFileName: 'robot/demo.urdf',
    preResolvedImports: [],
  };

  const serialized = await serializePreparedImportPayloadForWorker(payload);

  assert.equal(serialized.payload.assetFiles[0]?.mimeType, 'model/stl');
  assert.equal(serialized.payload.usdSourceFiles[0]?.mimeType, 'application/octet-stream');
  assert.equal(serialized.transferables.length, 2);

  const hydrated = hydratePreparedImportPayloadFromWorker(serialized.payload);

  assert.equal(hydrated.assetFiles[0]?.name, 'robot/meshes/base.stl');
  assert.equal(hydrated.usdSourceFiles[0]?.name, 'robot/usd/demo.usdc');
  assert.equal(await hydrated.assetFiles[0]?.blob.text(), 'solid demo');
  assert.deepEqual(
    Array.from(new Uint8Array(await hydrated.usdSourceFiles[0]!.blob.arrayBuffer())),
    [80, 88, 82, 45],
  );
  assert.deepEqual(hydrated.robotFiles, payload.robotFiles);
  assert.deepEqual(hydrated.libraryFiles, payload.libraryFiles);
  assert.deepEqual(hydrated.textFiles, payload.textFiles);
  assert.equal(hydrated.preferredFileName, payload.preferredFileName);
});

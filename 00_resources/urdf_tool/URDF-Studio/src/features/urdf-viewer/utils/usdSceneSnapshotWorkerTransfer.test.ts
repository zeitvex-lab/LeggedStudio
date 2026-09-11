import test from 'node:test';
import assert from 'node:assert/strict';

import type { UsdSceneSnapshot } from '@/types';

import {
  collectUsdSceneSnapshotTransferables,
  hasUsdSceneSnapshotHeavyBuffers,
  stripTransferHeavyUsdSceneSnapshotBuffers,
} from './usdSceneSnapshotWorkerTransfer.ts';

test('stripTransferHeavyUsdSceneSnapshotBuffers removes mesh buffers from the ready-critical payload', () => {
  const snapshot: UsdSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
    render: {
      meshDescriptors: [
        {
          meshId: '/Robot/base_link/visuals.proto_mesh_id0',
          sectionName: 'visuals',
          resolvedPrimPath: '/Robot/base_link/visuals/mesh_0',
          primType: 'mesh',
          ranges: {
            positions: { offset: 0, count: 9, stride: 3 },
            indices: { offset: 0, count: 3, stride: 1 },
          },
        },
      ],
    },
    buffers: {
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      indices: new Uint32Array([0, 1, 2]),
      normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
      uvs: new Float32Array([0, 0, 1, 0, 0, 1]),
      transforms: new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
      rangesByMeshId: {
        '/Robot/base_link/visuals.proto_mesh_id0': {
          positions: { offset: 0, count: 9, stride: 3 },
          indices: { offset: 0, count: 3, stride: 1 },
        },
      },
    },
  };

  assert.equal(hasUsdSceneSnapshotHeavyBuffers(snapshot), true);

  const stripped = stripTransferHeavyUsdSceneSnapshotBuffers(snapshot);

  assert.notEqual(stripped, snapshot);
  assert.deepEqual(stripped?.buffers, {
    rangesByMeshId: snapshot.buffers?.rangesByMeshId,
  });
  assert.equal((snapshot.buffers?.positions as Float32Array).length, 9);
});

test('collectUsdSceneSnapshotTransferables deduplicates shared typed-array buffers', () => {
  const sharedBuffer = new ArrayBuffer(Float32Array.BYTES_PER_ELEMENT * 12);
  const snapshot: UsdSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
    buffers: {
      positions: new Float32Array(sharedBuffer, 0, 6),
      normals: new Float32Array(sharedBuffer, Float32Array.BYTES_PER_ELEMENT * 6, 6),
    },
  };

  const transferables = collectUsdSceneSnapshotTransferables(snapshot);

  assert.deepEqual(transferables, [sharedBuffer]);
});

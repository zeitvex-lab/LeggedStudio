import test from 'node:test';
import assert from 'node:assert/strict';

import {
  parseUsdMeshObjectIndex,
  resolveUsdVisualMeshObjectOrder,
} from './usdRuntimeMeshObjectOrder.ts';

test('parseUsdMeshObjectIndex reads proto mesh suffix indices', () => {
  assert.equal(parseUsdMeshObjectIndex('/Robot/base_link/visuals.proto_mesh_id0'), 0);
  assert.equal(parseUsdMeshObjectIndex('/Robot/arm_link/visuals.proto_custom_id12'), 12);
  assert.equal(parseUsdMeshObjectIndex('/Robot/base_link/mesh'), undefined);
});

test('resolveUsdVisualMeshObjectOrder falls back to URDF truth proto index for non-proto mesh ids', () => {
  const order = resolveUsdVisualMeshObjectOrder({
    renderInterface: {
      getUrdfTruthLinkContextForMeshId: (meshId, sectionName) => {
        assert.equal(meshId, '/b2_description/base_link/visuals/mesh');
        assert.equal(sectionName, 'visuals');
        return {
          proto: {
            protoIndex: 4,
          },
        };
      },
    },
    meshId: '/b2_description/base_link/visuals/mesh',
    fallbackOrder: 0,
  });

  assert.equal(order, 4);
});

test('resolveUsdVisualMeshObjectOrder uses the provided fallback order when neither mesh id nor truth exposes an index', () => {
  const order = resolveUsdVisualMeshObjectOrder({
    renderInterface: {
      getUrdfTruthLinkContextForMeshId: () => null,
    },
    meshId: '/b2_description/base_link/visuals/mesh',
    fallbackOrder: 7,
  });

  assert.equal(order, 7);
});

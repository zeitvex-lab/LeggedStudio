import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LINK, GeometryType } from '../../../types/index.ts';
import {
  createSyntheticUsdViewerRobotResolution,
  resolveUsdRuntimeLinkPathForMesh,
} from './usdRuntimeMeshMapping';

test('creates a synthetic single-root resolution for generic USD scenes', () => {
  const resolution = createSyntheticUsdViewerRobotResolution({
    fileName: 'spherebot2.usdz',
    stageSourcePath: '/spherebot2.usdz',
    meshIds: [
      '/root/root_0/Body_1/Shell_2/primitive_0',
      '/root/root_0/Body_1/Eye_3/primitive_0',
    ],
  });

  assert.equal(resolution.runtimeLinkMappingMode, 'synthetic-root');
  assert.equal(resolution.robotData.name, 'spherebot2');
  assert.equal(resolution.robotData.rootLinkId, 'usd_scene_root');
  assert.deepEqual(Object.keys(resolution.robotData.links), ['usd_scene_root']);
  assert.equal(resolution.linkPathById.usd_scene_root, '/root/root_0/Body_1');
  assert.equal(resolution.linkIdByPath['/root/root_0/Body_1'], 'usd_scene_root');
});

test('resolves robot-style runtime mesh ids directly', () => {
  const linkPath = resolveUsdRuntimeLinkPathForMesh({
    meshId: '/Robot/base_link/visuals.proto_mesh_id0',
  });

  assert.equal(linkPath, '/Robot/base_link');
});

test('resolves robot-style /colliders runtime mesh ids to their owning link', () => {
  assert.equal(
    resolveUsdRuntimeLinkPathForMesh({
      meshId: '/Robot/base_link/colliders.proto_mesh_id0',
    }),
    '/Robot/base_link',
  );
  assert.equal(
    resolveUsdRuntimeLinkPathForMesh({
      meshId: '/Robot/base_link/colliders/mesh_0',
    }),
    '/Robot/base_link',
  );
  assert.equal(
    resolveUsdRuntimeLinkPathForMesh({
      meshId: '/Robot/base_link/collider.proto_mesh_id0',
    }),
    '/Robot/base_link',
  );
});

test('resolves generic runtime mesh ids through known ancestor link paths', () => {
  const resolution = {
    stageSourcePath: '/generic.usdz',
    runtimeLinkMappingMode: 'robot-data' as const,
    linkIdByPath: {
      '/root/root_0': 'root_link',
      '/root/root_0/Body_1': 'body_link',
    },
    linkPathById: {
      root_link: '/root/root_0',
      body_link: '/root/root_0/Body_1',
    },
    jointPathById: {},
    childLinkPathByJointId: {},
    parentLinkPathByJointId: {},
    robotData: {
      name: 'generic',
      rootLinkId: 'root_link',
      links: {
        root_link: {
          ...DEFAULT_LINK,
          id: 'root_link',
          name: 'root_link',
          visual: {
            ...DEFAULT_LINK.visual,
            type: GeometryType.MESH,
          },
        },
        body_link: {
          ...DEFAULT_LINK,
          id: 'body_link',
          name: 'body_link',
          visual: {
            ...DEFAULT_LINK.visual,
            type: GeometryType.MESH,
          },
        },
      },
      joints: {},
    },
  };

  const linkPath = resolveUsdRuntimeLinkPathForMesh({
    meshId: '/root/root_0/Body_1/Shell_2/primitive_0',
    resolvedPrimPath: '/root/root_0/Body_1/Shell_2/primitive_0',
    resolution,
  });

  assert.equal(linkPath, '/root/root_0/Body_1');
});

test('falls back to the synthetic root link path when a generic mesh has no explicit match', () => {
  const resolution = createSyntheticUsdViewerRobotResolution({
    fileName: 'spherebot2.usdz',
    stageSourcePath: '/spherebot2.usdz',
    meshIds: [
      '/root/root_0/Body_1/Shell_2/primitive_0',
    ],
  });

  const linkPath = resolveUsdRuntimeLinkPathForMesh({
    meshId: '/totally/unrelated/primitive_0',
    resolution,
  });

  assert.equal(linkPath, resolution.linkPathById.usd_scene_root);
});

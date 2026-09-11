import test from 'node:test';
import assert from 'node:assert/strict';

import { GeometryType, JointType } from '@/types';
import type { RobotState, UsdPreparedExportCache } from '@/types';
import { resolveCurrentUsdExportBundle } from './usdExportContext.ts';
import { mergeCurrentRobotWithSnapshotMeshPaths } from '@/features/urdf-viewer/utils/usd-export/usdExportRobotMerge';

function createCurrentRobot(): RobotState {
  return {
    name: 'edited_robot',
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
    links: {
      base_link: {
        id: 'base_link',
        name: 'base_link',
        visible: true,
        visual: {
          type: GeometryType.MESH,
          dimensions: { x: 2, y: 2, z: 2 },
          color: '#ff0000',
          origin: { xyz: { x: 1, y: 2, z: 3 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        collision: {
          type: GeometryType.NONE,
          dimensions: { x: 0, y: 0, z: 0 },
          color: '#00ff00',
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        },
        inertial: {
          mass: 1,
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
        },
      },
    },
    joints: {},
  };
}

function createSnapshot() {
  return {
    stageSourcePath: '/robots/demo/demo.usd',
    stage: {
      defaultPrimPath: '/Robot',
    },
    robotTree: {
      linkParentPairs: [['/Robot/base_link', null]],
      rootLinkPaths: ['/Robot/base_link'],
    },
    robotMetadataSnapshot: {
      stageSourcePath: '/robots/demo/demo.usd',
      linkParentPairs: [['/Robot/base_link', null]],
      jointCatalogEntries: [],
      meshCountsByLinkPath: {
        '/Robot/base_link': {
          visualMeshCount: 1,
          collisionMeshCount: 0,
        },
      },
    },
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
      normals: new Float32Array(0),
      uvs: new Float32Array(0),
      transforms: new Float32Array(0),
      rangesByMeshId: {},
    },
  };
}

function createPreparedCache(): UsdPreparedExportCache {
  return {
    stageSourcePath: '/robots/demo/demo.usd',
    robotData: {
      name: 'prepared_robot',
      rootLinkId: 'base_link',
      links: {
        base_link: {
          id: 'base_link',
          name: 'base_link',
          visible: true,
          visual: {
            type: GeometryType.MESH,
            dimensions: { x: 1, y: 1, z: 1 },
            color: '#ffffff',
            meshPath: 'base_link_visual_0.obj',
            origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          },
          collision: {
            type: GeometryType.NONE,
            dimensions: { x: 0, y: 0, z: 0 },
            color: '#cccccc',
            origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          },
          inertial: {
            mass: 1,
            origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
          },
        },
      },
      joints: {},
    },
    meshFiles: {
      'base_link_visual_0.obj': new Blob(['o cached_mesh\nv 0 0 0\nf 1 1 1\n'], {
        type: 'text/plain',
      }),
    },
  };
}

test('resolveCurrentUsdExportBundle falls back to prepared cache when no live snapshot is available', async () => {
  const bundle = resolveCurrentUsdExportBundle({
    stageSourcePath: '/robots/demo/demo.usd',
    currentRobot: createCurrentRobot(),
    cachedSnapshot: null,
    preparedCache: createPreparedCache(),
  });

  assert.ok(bundle);
  assert.equal(bundle.robot.name, 'edited_robot');
  assert.equal(bundle.robot.links.base_link.visual.meshPath, 'base_link_visual_0.obj');
  const meshText = await bundle.meshFiles.get('base_link_visual_0.obj')?.text();
  assert.match(meshText || '', /^o cached_mesh/m);
});

test('resolveCurrentUsdExportBundle prefers prepared cache over raw live snapshot when both are available', async () => {
  const bundle = resolveCurrentUsdExportBundle({
    stageSourcePath: '/robots/demo/demo.usd',
    currentRobot: createCurrentRobot(),
    cachedSnapshot: createSnapshot(),
    preparedCache: createPreparedCache(),
  });

  assert.ok(bundle);
  assert.equal(bundle.robot.name, 'edited_robot');
  assert.equal(bundle.robot.links.base_link.visual.meshPath, 'base_link_visual_0.obj');
  const meshText = await bundle.meshFiles.get('base_link_visual_0.obj')?.text();
  assert.match(meshText || '', /^o cached_mesh/m);
});

test('resolveCurrentUsdExportBundle preserves prepared USD materials over default current robot colors', () => {
  const currentRobot = createCurrentRobot();
  currentRobot.links.base_link.visual.color = '#808080';
  currentRobot.materials = {
    base_link: {
      color: '#808080',
    },
  };

  const preparedCache = createPreparedCache();
  preparedCache.robotData.links.base_link.visual.color = '#050505';
  preparedCache.robotData.links.base_link.visual.authoredMaterials = [
    {
      name: 'material_______024',
      color: '#050505',
    },
  ];
  preparedCache.robotData.links.base_link.visual.materialSource = 'named';
  preparedCache.robotData.materials = {
    base_link: {
      color: '#050505',
    },
  };

  const bundle = resolveCurrentUsdExportBundle({
    stageSourcePath: '/robots/unitree_model/B2/usd/b2.usd',
    currentRobot,
    cachedSnapshot: null,
    preparedCache,
  });

  assert.ok(bundle);
  assert.equal(bundle.robot.links.base_link.visual.color, '#050505');
  assert.deepEqual(bundle.robot.links.base_link.visual.authoredMaterials, [
    {
      name: 'material_______024',
      color: '#050505',
    },
  ]);
  assert.equal(bundle.robot.materials?.base_link?.color, '#050505');
});

test('resolveCurrentUsdExportBundle never revives entities deleted from the canonical robot', () => {
  const currentRobot = createCurrentRobot();
  const preparedCache = createPreparedCache();
  preparedCache.robotData.links.deleted_link = {
    ...structuredClone(preparedCache.robotData.links.base_link!),
    id: 'deleted_link',
    name: 'deleted_link',
  };
  preparedCache.robotData.joints.deleted_joint = {
    id: 'deleted_joint',
    name: 'deleted_joint',
    type: JointType.FIXED,
    parentLinkId: 'base_link',
    childLinkId: 'deleted_link',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    dynamics: { damping: 0, friction: 0 },
    hardware: {
      armature: 0,
      motorType: '',
      motorId: '',
      motorDirection: 1,
    },
  };

  const bundle = resolveCurrentUsdExportBundle({
    stageSourcePath: '/robots/demo/demo.usd',
    currentRobot,
    preparedCache,
  });

  assert.ok(bundle);
  assert.deepEqual(Object.keys(bundle.robot.links), ['base_link']);
  assert.deepEqual(bundle.robot.joints, {});
});

test('resolveCurrentUsdExportBundle keeps deleted visual and collision bodies deleted', () => {
  const currentRobot = createCurrentRobot();
  currentRobot.links.base_link!.visual = {
    ...currentRobot.links.base_link!.visual,
    type: GeometryType.NONE,
    dimensions: { x: 0, y: 0, z: 0 },
    meshPath: undefined,
  };
  currentRobot.links.base_link!.collisionBodies = [];

  const preparedCache = createPreparedCache();
  preparedCache.robotData.links.base_link!.visualBodies = [{
    ...structuredClone(preparedCache.robotData.links.base_link!.visual),
    meshPath: 'deleted_visual.obj',
  }];
  preparedCache.robotData.links.base_link!.collisionBodies = [{
    ...structuredClone(preparedCache.robotData.links.base_link!.visual),
    meshPath: 'deleted_collision.obj',
  }];

  const bundle = resolveCurrentUsdExportBundle({
    stageSourcePath: '/robots/demo/demo.usd',
    currentRobot,
    preparedCache,
  });

  assert.ok(bundle);
  assert.equal(bundle.robot.links.base_link!.visual.type, GeometryType.NONE);
  assert.equal(bundle.robot.links.base_link!.visual.meshPath, undefined);
  assert.equal(bundle.robot.links.base_link!.visualBodies, undefined);
  assert.deepEqual(bundle.robot.links.base_link!.collisionBodies, []);
});

test('resolveCurrentUsdExportBundle rejects malformed prepared RobotData before runtime iteration', () => {
  const preparedCache = createPreparedCache();
  (preparedCache.robotData.links.base_link!.visual as unknown as { authoredMaterials: unknown })
    .authoredMaterials = {};

  assert.throws(
    () => resolveCurrentUsdExportBundle({
      stageSourcePath: '/robots/demo/demo.usd',
      currentRobot: createCurrentRobot(),
      preparedCache,
    }),
    /USD prepared cache\.robotData\.links\.base_link\.visual\.authoredMaterials/i,
  );
});

test('snapshot fallback never revives canonical links, joints, or geometry bodies', () => {
  const currentRobot = createCurrentRobot();
  currentRobot.links.base_link!.visualBodies = [];
  const snapshotRobot: RobotState = {
    ...structuredClone(createPreparedCache().robotData),
    selection: { type: null, id: null },
  };
  snapshotRobot.links.deleted_link = {
    ...structuredClone(snapshotRobot.links.base_link!),
    id: 'deleted_link',
    name: 'deleted_link',
  };
  snapshotRobot.links.base_link!.visualBodies = [{
    ...structuredClone(snapshotRobot.links.base_link!.visual),
    meshPath: 'deleted_visual.obj',
  }];
  snapshotRobot.joints.deleted_joint = {
    id: 'deleted_joint',
    name: 'deleted_joint',
    type: JointType.FIXED,
    parentLinkId: 'base_link',
    childLinkId: 'deleted_link',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    dynamics: { damping: 0, friction: 0 },
    hardware: { armature: 0, motorType: '', motorId: '', motorDirection: 1 },
  };

  const merged = mergeCurrentRobotWithSnapshotMeshPaths(currentRobot, snapshotRobot);

  assert.deepEqual(Object.keys(merged.links), ['base_link']);
  assert.deepEqual(merged.joints, {});
  assert.deepEqual(merged.links.base_link!.visualBodies, []);
});

import test from 'node:test';
import assert from 'node:assert/strict';

import { prepareUsdExportCacheFromSnapshot } from '@/features/editor/usd_export';
import type { ViewerRobotDataResolution } from '@/features/editor/usd_hydration';
import { DEFAULT_LINK, GeometryType } from '@/types';

import {
  buildUsdHydrationPersistencePlan,
  resolveUsdHydrationRobotData,
} from './usdHydrationPersistence.ts';

const EMPTY_ROBOT_DATA = {
  name: 'demo',
  rootLinkId: 'base_link',
  links: {},
  joints: {},
};

test('buildUsdHydrationPersistencePlan seeds missing USD export fallbacks from the first hydration result', () => {
  const usdSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
  };

  const plan = buildUsdHydrationPersistencePlan({
    resolution: {
      robotData: EMPTY_ROBOT_DATA,
      usdSceneSnapshot,
    },
    existingSceneSnapshot: null,
    existingPreparedExportCache: null,
  });

  assert.equal(plan.sceneSnapshot, usdSceneSnapshot);
  assert.equal(plan.bakedScene, usdSceneSnapshot);
  assert.equal(plan.shouldSeedSceneSnapshot, true);
  assert.equal(plan.shouldSeedBakedScene, true);
  assert.equal(plan.shouldSeedPreparedExportCache, true);
});

test('buildUsdHydrationPersistencePlan accepts baked scene naming as the preferred USD payload', () => {
  const usdBakedScene = {
    stageSourcePath: '/robots/demo/demo.usd',
  };

  const plan = buildUsdHydrationPersistencePlan({
    resolution: {
      robotData: EMPTY_ROBOT_DATA,
      usdBakedScene,
    },
    existingSceneSnapshot: null,
    existingPreparedExportCache: null,
  });

  assert.equal(plan.bakedScene, usdBakedScene);
  assert.equal(plan.sceneSnapshot, usdBakedScene);
  assert.equal(plan.shouldSeedBakedScene, true);
  assert.equal(plan.shouldSeedSceneSnapshot, true);
});

test('buildUsdHydrationPersistencePlan preserves any existing USD export fallbacks', () => {
  const existingSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
  };
  const existingPreparedExportCache = {
    stageSourcePath: '/robots/demo/demo.usd',
    robotData: {
      name: 'prepared_robot',
      rootLinkId: 'base_link',
      links: {},
      joints: {},
    },
    meshFiles: {},
  };

  const plan = buildUsdHydrationPersistencePlan({
    resolution: {
      robotData: EMPTY_ROBOT_DATA,
      usdSceneSnapshot: null,
    },
    existingSceneSnapshot,
    existingPreparedExportCache,
  });

  assert.equal(plan.sceneSnapshot, existingSceneSnapshot);
  assert.equal(plan.shouldSeedSceneSnapshot, false);
  assert.equal(plan.shouldSeedPreparedExportCache, false);
});

test('resolveUsdHydrationRobotData prefers prepared cache robot data during the first USD hydration', () => {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  const indices = new Uint32Array([0, 1, 2]);
  const usdSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
    stage: {
      defaultPrimPath: '/Robot',
    },
    robotTree: {
      linkParentPairs: [['/Robot/base_link', null]] as Array<[string, string | null]>,
      rootLinkPaths: ['/Robot/base_link'],
    },
    robotMetadataSnapshot: {
      stageSourcePath: '/robots/demo/demo.usd',
      linkParentPairs: [['/Robot/base_link', null]] as Array<[string, string | null]>,
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
      positions,
      indices,
      normals: new Float32Array(0),
      uvs: new Float32Array(0),
      transforms: new Float32Array(0),
      rangesByMeshId: {},
    },
  };

  const resolution: ViewerRobotDataResolution & { usdSceneSnapshot: typeof usdSceneSnapshot } = {
    stageSourcePath: '/robots/demo/demo.usd',
    usdSceneSnapshot,
    linkIdByPath: {
      '/Robot/base_link': 'base_link',
    },
    linkPathById: {
      base_link: '/Robot/base_link',
    },
    jointPathById: {},
    childLinkPathByJointId: {},
    parentLinkPathByJointId: {},
    robotData: {
      name: 'demo',
      rootLinkId: 'base_link',
      links: {
        base_link: {
          ...DEFAULT_LINK,
          id: 'base_link',
          name: 'base_link',
          visual: {
            ...DEFAULT_LINK.visual,
            type: GeometryType.MESH,
            meshPath: undefined,
          },
        },
      },
      joints: {},
    },
  };

  const hydrated = resolveUsdHydrationRobotData({
    resolution,
    existingPreparedExportCache: null,
    prepareExportCacheFromSnapshot: prepareUsdExportCacheFromSnapshot,
  });

  assert.match(
    hydrated.robotData.links.base_link.visual.meshPath || '',
    /base_link_visual_0\.obj$/,
  );
  assert.ok(hydrated.preparedExportCache);
  assert.equal(Object.keys(hydrated.preparedExportCache?.meshFiles || {}).length, 1);
});

test('resolveUsdHydrationRobotData can skip synchronous prepared cache materialization on the hydration hot path', () => {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  const indices = new Uint32Array([0, 1, 2]);
  const usdSceneSnapshot = {
    stageSourcePath: '/robots/demo/demo.usd',
    stage: {
      defaultPrimPath: '/Robot',
    },
    robotTree: {
      linkParentPairs: [['/Robot/base_link', null]] as Array<[string, string | null]>,
      rootLinkPaths: ['/Robot/base_link'],
    },
    robotMetadataSnapshot: {
      stageSourcePath: '/robots/demo/demo.usd',
      linkParentPairs: [['/Robot/base_link', null]] as Array<[string, string | null]>,
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
      positions,
      indices,
      normals: new Float32Array(0),
      uvs: new Float32Array(0),
      transforms: new Float32Array(0),
      rangesByMeshId: {},
    },
  };

  const resolution: ViewerRobotDataResolution & { usdSceneSnapshot: typeof usdSceneSnapshot } = {
    stageSourcePath: '/robots/demo/demo.usd',
    usdSceneSnapshot,
    linkIdByPath: {
      '/Robot/base_link': 'base_link',
    },
    linkPathById: {
      base_link: '/Robot/base_link',
    },
    jointPathById: {},
    childLinkPathByJointId: {},
    parentLinkPathByJointId: {},
    robotData: {
      name: 'demo',
      rootLinkId: 'base_link',
      links: {
        base_link: {
          ...DEFAULT_LINK,
          id: 'base_link',
          name: 'base_link',
          visual: {
            ...DEFAULT_LINK.visual,
            type: GeometryType.MESH,
            meshPath: undefined,
          },
        },
      },
      joints: {},
    },
  };

  const hydrated = resolveUsdHydrationRobotData({
    resolution,
    allowSynchronousPreparedCacheFromSnapshot: false,
    existingPreparedExportCache: null,
    prepareExportCacheFromSnapshot: prepareUsdExportCacheFromSnapshot,
  });

  assert.equal(hydrated.robotData, resolution.robotData);
  assert.equal(hydrated.preparedExportCache, null);
  assert.equal(hydrated.robotData.links.base_link.visual.meshPath, undefined);
});

test('resolveUsdHydrationRobotData ignores stale prepared cache robot data when a fresh USD scene snapshot is present', () => {
  const resolution: ViewerRobotDataResolution & { usdSceneSnapshot: { stageSourcePath: string } } =
    {
      stageSourcePath: '/robots/demo/demo.usd',
      usdSceneSnapshot: {
        stageSourcePath: '/robots/demo/demo.usd',
      },
      linkIdByPath: {},
      linkPathById: {},
      jointPathById: {},
      childLinkPathByJointId: {},
      parentLinkPathByJointId: {},
      robotData: {
        name: 'fresh_robot',
        rootLinkId: 'base_link',
        links: {},
        joints: {},
      },
    };

  const existingPreparedExportCache = {
    stageSourcePath: '/robots/demo/demo.usd',
    robotData: {
      name: 'stale_robot',
      rootLinkId: 'stale_root',
      links: {},
      joints: {},
    },
    meshFiles: {},
  };

  const hydrated = resolveUsdHydrationRobotData({
    resolution,
    allowSynchronousPreparedCacheFromSnapshot: false,
    existingPreparedExportCache,
    prepareExportCacheFromSnapshot: prepareUsdExportCacheFromSnapshot,
  });

  assert.equal(hydrated.robotData, resolution.robotData);
  assert.equal(hydrated.preparedExportCache, null);
});

test('resolveUsdHydrationRobotData can still fall back to prepared cache robot data when no fresh USD scene snapshot is available', () => {
  const resolution: ViewerRobotDataResolution = {
    stageSourcePath: '/robots/demo/demo.usd',
    usdSceneSnapshot: null,
    linkIdByPath: {},
    linkPathById: {},
    jointPathById: {},
    childLinkPathByJointId: {},
    parentLinkPathByJointId: {},
    robotData: EMPTY_ROBOT_DATA,
  };

  const existingPreparedExportCache = {
    stageSourcePath: '/robots/demo/demo.usd',
    robotData: {
      name: 'prepared_robot',
      rootLinkId: 'base_link',
      links: {},
      joints: {},
    },
    meshFiles: {},
  };

  const hydrated = resolveUsdHydrationRobotData({
    resolution,
    allowSynchronousPreparedCacheFromSnapshot: false,
    existingPreparedExportCache,
    prepareExportCacheFromSnapshot: prepareUsdExportCacheFromSnapshot,
  });

  assert.equal(hydrated.robotData, existingPreparedExportCache.robotData);
  assert.equal(hydrated.preparedExportCache, existingPreparedExportCache);
});

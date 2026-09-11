import test from 'node:test';
import assert from 'node:assert/strict';

import type { UsdSceneSnapshot } from '@/types';
import { resolveUsdSceneRobotResolution } from './usdSceneRobotResolution';

function createAdaptableSnapshot(): UsdSceneSnapshot {
  return {
    stageSourcePath: '/robots/unitree/b2.usd',
    stage: {
      defaultPrimPath: '/Robot',
    },
    robotTree: {
      linkParentPairs: [
        ['/Robot/base_link', null],
      ],
      rootLinkPaths: ['/Robot/base_link'],
    },
    robotMetadataSnapshot: {
      stageSourcePath: '/robots/unitree/b2.usd',
      linkParentPairs: [
        ['/Robot/base_link', null],
      ],
      jointCatalogEntries: [],
      linkDynamicsEntries: [],
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
          resolvedPrimPath: '/Robot/base_link/visuals/base_link',
          primType: 'mesh',
        },
      ],
    },
  };
}

function createEmptySnapshot(): UsdSceneSnapshot {
  return {
    stageSourcePath: '/robots/unitree/b2.usd',
    stage: {
      defaultPrimPath: '/Robot',
    },
    robotMetadataSnapshot: {
      stageSourcePath: '/robots/unitree/b2.usd',
      linkParentPairs: [],
      jointCatalogEntries: [],
      linkDynamicsEntries: [],
      meshCountsByLinkPath: {},
    },
    render: {
      meshDescriptors: [],
    },
  };
}

test('returns an adapted robot resolution from the cached USD scene snapshot without warmup', () => {
  const snapshot = createAdaptableSnapshot();
  let warmupCount = 0;

  const result = resolveUsdSceneRobotResolution({
    renderInterface: {
      getCachedRobotSceneSnapshot: () => snapshot,
      warmupRobotSceneSnapshotFromDriver: () => {
        warmupCount += 1;
      },
      meshes: {
        '/Robot/base_link/visuals.proto_mesh_id0': {},
      },
    },
    driver: {},
    stageSourcePath: '/robots/unitree/b2.usd',
    fileName: 'b2.usd',
  });

  assert.equal(warmupCount, 0);
  assert.equal(result.usedWarmup, false);
  assert.equal(result.resolution.runtimeLinkMappingMode, 'robot-data');
  assert.equal(result.resolution.robotData.rootLinkId, 'base_link');
});

test('warms up the USD scene snapshot when no cached snapshot exists yet', () => {
  let snapshot: UsdSceneSnapshot | null = null as UsdSceneSnapshot | null;
  const warmupCalls: boolean[] = [];

  const result = resolveUsdSceneRobotResolution({
    renderInterface: {
      getCachedRobotSceneSnapshot: () => snapshot,
      warmupRobotSceneSnapshotFromDriver: (_driver, options) => {
        warmupCalls.push(options?.force === true);
        snapshot = createAdaptableSnapshot();
      },
      meshes: {
        '/Robot/base_link/visuals.proto_mesh_id0': {},
      },
    },
    driver: {},
    stageSourcePath: '/robots/unitree/b2.usd',
    fileName: 'b2.usd',
  });

  assert.deepEqual(warmupCalls, [false]);
  assert.equal(result.usedWarmup, true);
  assert.equal(result.resolution.runtimeLinkMappingMode, 'robot-data');
  assert.equal(result.resolution.robotData.rootLinkId, 'base_link');
});

test('forces a robot metadata warmup when the cached snapshot would otherwise collapse into the synthetic USD root', () => {
  let snapshot: UsdSceneSnapshot | null = createEmptySnapshot();
  const warmupCalls: boolean[] = [];

  const result = resolveUsdSceneRobotResolution({
    renderInterface: {
      getCachedRobotSceneSnapshot: () => snapshot,
      warmupRobotSceneSnapshotFromDriver: (_driver, options) => {
        warmupCalls.push(options?.force === true);
        snapshot = createAdaptableSnapshot();
      },
      meshes: {
        '/Robot/base_link/visuals.proto_mesh_id0': {},
      },
    },
    driver: {},
    stageSourcePath: '/robots/unitree/b2.usd',
    fileName: 'b2.usd',
  });

  assert.deepEqual(warmupCalls, [true]);
  assert.equal(result.usedWarmup, true);
  assert.equal(result.resolution.runtimeLinkMappingMode, 'robot-data');
  assert.equal(result.resolution.robotData.rootLinkId, 'base_link');
});

test('falls back to the synthetic USD scene root when warmup cannot recover robot metadata', () => {
  const warmupCalls: boolean[] = [];

  const result = resolveUsdSceneRobotResolution({
    renderInterface: {
      getCachedRobotSceneSnapshot: () => createEmptySnapshot(),
      warmupRobotSceneSnapshotFromDriver: (_driver, options) => {
        warmupCalls.push(options?.force === true);
      },
      meshes: {
        '/World/geometry/Body_0/primitive_0': {},
      },
    },
    driver: {},
    stageSourcePath: '/robots/unitree/b2.usd',
    fileName: 'b2.usd',
  });

  assert.deepEqual(warmupCalls, [true]);
  assert.equal(result.usedWarmup, true);
  assert.equal(result.resolution.runtimeLinkMappingMode, 'synthetic-root');
  assert.equal(result.resolution.robotData.rootLinkId, 'usd_scene_root');
  assert.equal(result.resolution.linkPathById.usd_scene_root, '/Robot');
});

test('can skip warmup entirely and return a synthetic resolution from the current runtime mesh set', () => {
  let warmupCount = 0;

  const result = resolveUsdSceneRobotResolution({
    renderInterface: {
      getCachedRobotSceneSnapshot: () => null,
      warmupRobotSceneSnapshotFromDriver: () => {
        warmupCount += 1;
      },
      meshes: {
        '/World/geometry/Body_0/primitive_0': {},
      },
    },
    driver: {},
    stageSourcePath: '/robots/unitree/b2.usd',
    fileName: 'b2.usd',
    allowWarmup: false,
  });

  assert.equal(warmupCount, 0);
  assert.equal(result.usedWarmup, false);
  assert.equal(result.resolution.runtimeLinkMappingMode, 'synthetic-root');
  assert.equal(result.resolution.robotData.rootLinkId, 'usd_scene_root');
});

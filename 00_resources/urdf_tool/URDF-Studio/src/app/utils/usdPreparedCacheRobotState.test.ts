import test from 'node:test';
import assert from 'node:assert/strict';

import { DEFAULT_LINK, type RobotData, type UsdPreparedExportCache } from '@/types';
import { resolveUsdPreparedCacheRobotStateUpdate } from './usdPreparedCacheRobotState.ts';

function createRobotData(name: string): RobotData {
  return {
    name,
    rootLinkId: 'base_link',
    links: {
      base_link: {
        ...DEFAULT_LINK,
        id: 'base_link',
        name: 'base_link',
      },
    },
    joints: {},
    materials: {},
    closedLoopConstraints: [],
  };
}

test('resolveUsdPreparedCacheRobotStateUpdate replaces only RobotData in an existing cache', () => {
  const meshFile = new Blob(['o base\n'], { type: 'text/plain' });
  const existingCache: UsdPreparedExportCache = {
    stageSourcePath: '/robots/demo.usda',
    robotData: createRobotData('before'),
    meshFiles: {
      'base.obj': meshFile,
    },
  };
  const nextRobotData = createRobotData('after');

  const result = resolveUsdPreparedCacheRobotStateUpdate({
    existingPreparedExportCache: existingCache,
    robotData: nextRobotData,
  });

  assert.equal(result.status, 'updated');
  assert.equal(result.preparedExportCache?.robotData, nextRobotData);
  assert.equal(result.preparedExportCache?.meshFiles['base.obj'], meshFile);
  assert.equal(result.preparedExportCache?.stageSourcePath, '/robots/demo.usda');
  assert.notEqual(result.preparedExportCache, existingCache);
});

test('resolveUsdPreparedCacheRobotStateUpdate reports missing cache instead of rebuilding from a live USD scene', () => {
  const result = resolveUsdPreparedCacheRobotStateUpdate({
    existingPreparedExportCache: null,
    robotData: createRobotData('edited'),
  });

  assert.equal(result.status, 'missing-cache');
  assert.equal(result.preparedExportCache, null);
});

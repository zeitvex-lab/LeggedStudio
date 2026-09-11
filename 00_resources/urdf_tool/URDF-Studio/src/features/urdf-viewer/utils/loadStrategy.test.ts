import test from 'node:test';
import assert from 'node:assert/strict';

import {
  shouldForceViewerRuntimeRemount,
  shouldMountRobotBeforeAssetsComplete,
} from './loadStrategy.ts';

test('keeps URDF robots on the full-load path so the first visible frame uses final bounds', () => {
  assert.equal(shouldMountRobotBeforeAssetsComplete('urdf'), false);
});

test('keeps MJCF robots on the full-load path', () => {
  assert.equal(shouldMountRobotBeforeAssetsComplete('mjcf'), false);
});

test('only forces a full runtime remount for USD documents', () => {
  assert.equal(shouldForceViewerRuntimeRemount('urdf'), false);
  assert.equal(shouldForceViewerRuntimeRemount('mjcf'), false);
  assert.equal(shouldForceViewerRuntimeRemount('xacro'), false);
  assert.equal(shouldForceViewerRuntimeRemount('sdf'), false);
  assert.equal(shouldForceViewerRuntimeRemount('asset'), false);
  assert.equal(shouldForceViewerRuntimeRemount('usd'), true);
  assert.equal(shouldForceViewerRuntimeRemount('usda' as never), true);
});

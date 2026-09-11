import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getViewerRobotSourceFormat,
  resolvePreferredViewerRobotSourceFormat,
  resolveViewerRobotSourceFormat,
} from './sourceFormat';

test('getViewerRobotSourceFormat keeps SDF and Xacro on explicit viewer source branches', () => {
  assert.equal(getViewerRobotSourceFormat('sdf'), 'sdf');
  assert.equal(getViewerRobotSourceFormat('xacro'), 'xacro');
  assert.equal(getViewerRobotSourceFormat('urdf'), 'urdf');
  assert.equal(getViewerRobotSourceFormat('mjcf'), 'mjcf');
  assert.equal(getViewerRobotSourceFormat('usd'), 'usd');
  assert.equal(getViewerRobotSourceFormat(null), 'auto');
});

test('resolveViewerRobotSourceFormat normalizes SDF and Xacro viewer content to the URDF shading path', () => {
  assert.equal(resolveViewerRobotSourceFormat('<robot name="demo" />', 'sdf'), 'urdf');
  assert.equal(resolveViewerRobotSourceFormat('<robot name="demo" />', 'xacro'), 'urdf');
  assert.equal(resolveViewerRobotSourceFormat('<robot name="demo" />', 'urdf'), 'urdf');
});

test('resolveViewerRobotSourceFormat keeps MJCF explicit and auto-detects MJCF content', () => {
  assert.equal(resolveViewerRobotSourceFormat('<mujoco model="demo" />', 'mjcf'), 'mjcf');
  assert.equal(resolveViewerRobotSourceFormat('<mujoco model="demo" />', 'auto'), 'mjcf');
  assert.equal(resolveViewerRobotSourceFormat('<robot name="demo" />', 'auto'), 'urdf');
});

test('resolvePreferredViewerRobotSourceFormat keeps explicit viewer overrides ahead of source file format', () => {
  assert.equal(resolvePreferredViewerRobotSourceFormat('urdf', 'mjcf'), 'urdf');
  assert.equal(resolvePreferredViewerRobotSourceFormat('auto', 'mjcf'), 'auto');
  assert.equal(resolvePreferredViewerRobotSourceFormat(undefined, 'mjcf'), 'mjcf');
  assert.equal(resolvePreferredViewerRobotSourceFormat(undefined, 'usd'), 'usd');
});

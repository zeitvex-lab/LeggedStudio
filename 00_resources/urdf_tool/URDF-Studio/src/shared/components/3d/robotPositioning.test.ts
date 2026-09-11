import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  alignRobotToGroundBeforeFirstMount,
  beginInitialGroundAlignment,
  copyRobotRootTransform,
  hasInitialGroundAlignment,
  setInitialGroundAlignment,
  setPreserveAuthoredRootTransform,
  shouldPreserveAuthoredRootTransform,
} from './robotPositioning.ts';

test('preserve authored root transform flag is opt-in on runtime robots', () => {
  const robot = new THREE.Group();

  assert.equal(shouldPreserveAuthoredRootTransform(robot), false);

  setPreserveAuthoredRootTransform(robot, true);
  assert.equal(shouldPreserveAuthoredRootTransform(robot), true);

  setPreserveAuthoredRootTransform(robot, false);
  assert.equal(shouldPreserveAuthoredRootTransform(robot), false);
});

test('initial ground alignment only begins once per runtime robot', () => {
  const robot = new THREE.Group();

  assert.equal(hasInitialGroundAlignment(robot), false);
  assert.equal(beginInitialGroundAlignment(robot), true);
  assert.equal(hasInitialGroundAlignment(robot), true);
  assert.equal(beginInitialGroundAlignment(robot), false);
});

test('initial ground alignment flag can be reset for a final retry after assets finish loading', () => {
  const robot = new THREE.Group();

  assert.equal(beginInitialGroundAlignment(robot), true);
  assert.equal(hasInitialGroundAlignment(robot), true);

  setInitialGroundAlignment(robot, false);

  assert.equal(hasInitialGroundAlignment(robot), false);
  assert.equal(beginInitialGroundAlignment(robot), true);
});

test('aligns the robot to the ground before the first visible mount', () => {
  const robot = new THREE.Group();
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshBasicMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  mesh.userData.isVisualMesh = true;
  mesh.position.z = 2.5;
  robot.add(mesh);
  robot.updateMatrixWorld(true);

  const aligned = alignRobotToGroundBeforeFirstMount(robot, 0);

  assert.equal(aligned, true);
  assert.equal(hasInitialGroundAlignment(robot), true);

  const bounds = new THREE.Box3().setFromObject(mesh);
  assert.ok(Math.abs(bounds.min.z) < 1e-6);

  geometry.dispose();
  material.dispose();
});

test('copyRobotRootTransform preserves the previous runtime root transform state', () => {
  const previousRobot = new THREE.Group();
  previousRobot.position.set(1.25, -2.5, 3.75);
  previousRobot.quaternion.setFromEuler(new THREE.Euler(0.1, -0.2, 0.3));
  previousRobot.scale.set(1.1, 0.9, 1.2);
  setInitialGroundAlignment(previousRobot, true);
  setPreserveAuthoredRootTransform(previousRobot, true);

  const nextRobot = new THREE.Group();

  const copied = copyRobotRootTransform(previousRobot, nextRobot);

  assert.equal(copied, true);
  assert.deepEqual(nextRobot.position.toArray(), previousRobot.position.toArray());
  assert.deepEqual(nextRobot.quaternion.toArray(), previousRobot.quaternion.toArray());
  assert.deepEqual(nextRobot.scale.toArray(), previousRobot.scale.toArray());
  assert.equal(hasInitialGroundAlignment(nextRobot), true);
  assert.equal(shouldPreserveAuthoredRootTransform(nextRobot), true);
});

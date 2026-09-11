import assert from 'node:assert/strict';
import test from 'node:test';

import * as THREE from 'three';

import type { UrdfJoint } from '@/types';

import {
  extractJointActualAngleFromQuaternion,
  getJointMotionAngleFromActualAngle,
} from './kinematics';

function createJointFixture(
  referencePosition = Math.PI / 4,
): Pick<UrdfJoint, 'axis' | 'referencePosition'> {
  return {
    axis: { x: 0, y: 0, z: 1 },
    referencePosition,
  };
}

test('extractJointActualAngleFromQuaternion restores actual hinge angle from zero effective motion', () => {
  const joint = createJointFixture();
  const quaternion = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), 0);

  assert.ok(
    Math.abs(extractJointActualAngleFromQuaternion(joint, quaternion) - Math.PI / 4) < 1e-9,
  );
});

test('extractJointActualAngleFromQuaternion restores actual hinge angle from effective motion delta', () => {
  const joint = createJointFixture();
  const quaternion = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -0.2);

  assert.ok(
    Math.abs(extractJointActualAngleFromQuaternion(joint, quaternion) - (Math.PI / 4 - 0.2)) < 1e-9,
  );
});

test('getJointMotionAngleFromActualAngle keeps gizmo display in effective-motion space', () => {
  const joint = createJointFixture();

  assert.ok(Math.abs(getJointMotionAngleFromActualAngle(joint, Math.PI / 4)) < 1e-9);
  assert.ok(Math.abs(getJointMotionAngleFromActualAngle(joint, Math.PI / 4 - 0.2) + 0.2) < 1e-9);
});

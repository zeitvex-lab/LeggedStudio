import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import {
  FUSION_ROTATE_ARC_RADIUS,
  FUSION_ROTATE_E_RING_RADIUS,
  FUSION_ROTATE_FRONT_ARC_SPAN,
  createFusionRotateFrontArcGeometry,
  createFusionRotateFullRingGeometry,
  getFusionRotateArcPoint,
  getFusionRotateFrontArcCenterAngle,
  getFusionRotateFrontArcQuaternion,
  getFusionRotateScreenQuaternion,
  resolveFusionTrackballQuaternion,
} from './fusionRotateGeometry.ts';

const EPSILON = 1e-8;

const assertClose = (actual: number, expected: number, label: string) => {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${label}: ${actual} !== ${expected}`);
};

test('front arc center angle projects camera position into the axis ring plane', () => {
  assertClose(
    getFusionRotateFrontArcCenterAngle('X', new THREE.Vector3(0, 0, 1)),
    Math.PI / 2,
    'X ring camera +Z angle',
  );
  assertClose(
    getFusionRotateFrontArcCenterAngle('Y', new THREE.Vector3(0, 0, 1)),
    Math.PI / 2,
    'Y ring camera +Z angle',
  );
  assertClose(
    getFusionRotateFrontArcCenterAngle('Z', new THREE.Vector3(0, 1, 0)),
    Math.PI / 2,
    'Z ring camera +Y angle',
  );
});

test('front arc quaternion rotates the canonical half arc toward the camera angle', () => {
  const yRingPoint = getFusionRotateArcPoint('Y', 0)
    .applyQuaternion(getFusionRotateFrontArcQuaternion('Y', Math.PI / 2));

  assertClose(yRingPoint.x, 0, 'Y ring rotated X');
  assertClose(yRingPoint.z, FUSION_ROTATE_ARC_RADIUS, 'Y ring rotated Z');
});

test('screen quaternion aligns the E ring normal with the camera direction', () => {
  const cameraDirection = new THREE.Vector3(1, 2, 3).normalize();
  const normal = new THREE.Vector3(0, 0, 1)
    .applyQuaternion(getFusionRotateScreenQuaternion(cameraDirection));

  assert.ok(normal.distanceTo(cameraDirection) < EPSILON);
});

test('rotate geometries keep full rings and front arcs on the configured radii', () => {
  const frontArc = createFusionRotateFrontArcGeometry('Z', 0.01);
  const fullRing = createFusionRotateFullRingGeometry('Z', 0.01, FUSION_ROTATE_E_RING_RADIUS);

  frontArc.computeBoundingSphere();
  fullRing.computeBoundingSphere();

  assert.ok(frontArc.boundingSphere);
  assert.ok(fullRing.boundingSphere);
  assert.ok((frontArc.boundingSphere?.radius ?? 0) > FUSION_ROTATE_ARC_RADIUS * 0.5);
  assert.ok((fullRing.boundingSphere?.radius ?? 0) > FUSION_ROTATE_E_RING_RADIUS);
  assertClose(FUSION_ROTATE_FRONT_ARC_SPAN, Math.PI, 'front arc span');

  frontArc.dispose();
  fullRing.dispose();
});

test('trackball rotation converts screen-plane deltas into parent-space quaternions', () => {
  const start = new THREE.Quaternion();
  const next = resolveFusionTrackballQuaternion({
    cameraRightWorld: new THREE.Vector3(1, 0, 0),
    cameraUpWorld: new THREE.Vector3(0, 1, 0),
    deltaWorld: new THREE.Vector3(0.1, -0.05, 0),
    parentWorldQuaternionInv: new THREE.Quaternion(),
    radius: 0.5,
    startQuaternion: start,
  });

  assert.ok(Math.abs(next.length() - 1) < EPSILON);
  assert.ok(next.angleTo(start) > 0.01);
});

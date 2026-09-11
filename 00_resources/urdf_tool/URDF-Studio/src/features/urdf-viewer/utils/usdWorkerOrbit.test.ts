import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  applyUsdWorkerOrbitPanDelta,
  applyUsdWorkerOrbitPointerDelta,
  applyUsdWorkerOrbitToCamera,
  applyUsdWorkerOrbitZoomDelta,
  createUsdWorkerOrbitState,
} from './usdWorkerOrbit.ts';

function assertApprox(actual: number, expected: number, epsilon = 1e-6): void {
  assert.ok(Math.abs(actual - expected) <= epsilon, `Expected ${actual} to be within ${epsilon} of ${expected}`);
}

function assertVectorApprox(actual: THREE.Vector3, expected: THREE.Vector3, epsilon = 1e-6): void {
  assertApprox(actual.x, expected.x, epsilon);
  assertApprox(actual.y, expected.y, epsilon);
  assertApprox(actual.z, expected.z, epsilon);
}

function applyOrbitControlsReferencePointerDelta({
  position,
  target,
  up,
  deltaX,
  deltaY,
  rotationSpeed,
}: {
  position: THREE.Vector3;
  target: THREE.Vector3;
  up: THREE.Vector3;
  deltaX: number;
  deltaY: number;
  rotationSpeed: number;
}): THREE.Vector3 {
  const yAxis = new THREE.Vector3(0, 1, 0);
  const offset = position.clone().sub(target);
  const quat = new THREE.Quaternion().setFromUnitVectors(up, yAxis);
  const quatInverse = quat.clone().invert();
  const spherical = new THREE.Spherical();

  offset.applyQuaternion(quat);
  spherical.setFromVector3(offset);
  spherical.theta -= deltaX * rotationSpeed;
  spherical.phi -= deltaY * rotationSpeed;
  spherical.makeSafe();

  offset.setFromSpherical(spherical);
  offset.applyQuaternion(quatInverse);

  return target.clone().add(offset);
}

function applyOrbitControlsReferencePanDelta({
  camera,
  target,
  deltaX,
  deltaY,
  viewportHeight,
  panSpeed,
}: {
  camera: THREE.PerspectiveCamera;
  target: THREE.Vector3;
  deltaX: number;
  deltaY: number;
  viewportHeight: number;
  panSpeed: number;
}): THREE.Vector3 {
  const offset = camera.position.clone().sub(target);
  const targetDistance = offset.length() * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const panOffset = new THREE.Vector3();
  const column = new THREE.Vector3();

  column.setFromMatrixColumn(camera.matrix, 0);
  column.multiplyScalar((-2 * deltaX * targetDistance * panSpeed) / viewportHeight);
  panOffset.add(column);

  column.setFromMatrixColumn(camera.matrix, 1);
  column.multiplyScalar((2 * deltaY * targetDistance * panSpeed) / viewportHeight);
  panOffset.add(column);

  return target.clone().add(panOffset);
}

test('createUsdWorkerOrbitState round-trips the camera position through applyUsdWorkerOrbitToCamera', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(2.6, -2.6, 4.6);
  const target = new THREE.Vector3(0, 0, 0);

  const orbit = createUsdWorkerOrbitState(camera.position, target);
  camera.position.set(0, 0, 0);

  applyUsdWorkerOrbitToCamera(orbit, camera);

  assertApprox(camera.position.x, 2.6);
  assertApprox(camera.position.y, -2.6);
  assertApprox(camera.position.z, 4.6);
});

test('applyUsdWorkerOrbitPointerDelta matches OrbitControls vertical rotation in a Z-up scene', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(2.6, -2.6, 4.6);
  camera.up.set(0, 0, 1);
  const target = new THREE.Vector3(0, 0, 0);
  const rotationSpeed = 0.01;

  const expected = applyOrbitControlsReferencePointerDelta({
    position: camera.position,
    target,
    up: camera.up,
    deltaX: 0,
    deltaY: 100,
    rotationSpeed,
  });

  const orbit = createUsdWorkerOrbitState(camera.position, target);
  applyUsdWorkerOrbitPointerDelta(orbit, 0, 100, { rotationSpeed });
  applyUsdWorkerOrbitToCamera(orbit, camera);

  assertVectorApprox(camera.position, expected);
});

test('applyUsdWorkerOrbitPointerDelta matches OrbitControls horizontal rotation in a Z-up scene', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(2.6, -2.6, 4.6);
  camera.up.set(0, 0, 1);
  const target = new THREE.Vector3(0, 0, 0);
  const rotationSpeed = 0.01;

  const expected = applyOrbitControlsReferencePointerDelta({
    position: camera.position,
    target,
    up: camera.up,
    deltaX: 100,
    deltaY: 0,
    rotationSpeed,
  });

  const orbit = createUsdWorkerOrbitState(camera.position, target);
  applyUsdWorkerOrbitPointerDelta(orbit, 100, 0, { rotationSpeed });
  applyUsdWorkerOrbitToCamera(orbit, camera);

  assertVectorApprox(camera.position, expected);
});

test('applyUsdWorkerOrbitPanDelta matches OrbitControls perspective screen-space pan', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(2.6, -2.6, 4.6);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const target = new THREE.Vector3(0, 0, 0);
  const viewportHeight = 556;
  const panSpeed = 0.9;

  const expectedTarget = applyOrbitControlsReferencePanDelta({
    camera,
    target,
    deltaX: 120,
    deltaY: 80,
    viewportHeight,
    panSpeed,
  });
  const expectedPosition = camera.position.clone().add(expectedTarget.clone().sub(target));

  const orbit = createUsdWorkerOrbitState(camera.position, target);
  applyUsdWorkerOrbitPanDelta(orbit, camera, 120, 80, {
    viewportHeight,
    panSpeed,
  });
  applyUsdWorkerOrbitToCamera(orbit, camera);

  assertVectorApprox(orbit.target, expectedTarget);
  assertVectorApprox(camera.position, expectedPosition);
});

test('applyUsdWorkerOrbitToCamera syncs the controls target after panning', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(2.6, -2.6, 4.6);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const controls = { target: new THREE.Vector3(0, 0, 0) };
  const orbit = createUsdWorkerOrbitState(camera.position, controls.target);

  applyUsdWorkerOrbitPanDelta(orbit, camera, 120, 80, {
    viewportHeight: 556,
    panSpeed: 0.9,
  });
  applyUsdWorkerOrbitToCamera(orbit, camera, controls);

  assertVectorApprox(controls.target, orbit.target);
});

test('applyUsdWorkerOrbitPanDelta supports damped pan speed for large-scene navigation', () => {
  const camera = new THREE.PerspectiveCamera(68, 1, 0.1, 1000);
  camera.position.set(25, 0, 5);
  camera.up.set(0, 0, 1);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  const target = new THREE.Vector3(0, 0, 0);

  const baseOrbit = createUsdWorkerOrbitState(camera.position, target);
  applyUsdWorkerOrbitPanDelta(baseOrbit, camera, 120, 80, {
    viewportHeight: 556,
    panSpeed: 0.9,
  });

  const dampedOrbit = createUsdWorkerOrbitState(camera.position, target);
  applyUsdWorkerOrbitPanDelta(dampedOrbit, camera, 120, 80, {
    viewportHeight: 556,
    panSpeed: 0.9 * 0.35,
  });

  assert.ok(
    dampedOrbit.target.distanceTo(target) < baseOrbit.target.distanceTo(target),
    'expected a scale-aware pan speed to reduce USD worker pan travel',
  );
});

test('applyUsdWorkerOrbitPointerDelta clamps the polar angle away from the singularities', () => {
  const orbit = createUsdWorkerOrbitState(
    new THREE.Vector3(0, -2, 2),
    new THREE.Vector3(0, 0, 0),
  );

  applyUsdWorkerOrbitPointerDelta(orbit, 0, -10_000);
  assert.ok(orbit.polar > 0);

  applyUsdWorkerOrbitPointerDelta(orbit, 0, 10_000);
  assert.ok(orbit.polar < Math.PI);
});

test('applyUsdWorkerOrbitZoomDelta keeps the radius inside the provided clamp window', () => {
  const orbit = createUsdWorkerOrbitState(
    new THREE.Vector3(0, -3, 3),
    new THREE.Vector3(0, 0, 0),
  );

  applyUsdWorkerOrbitZoomDelta(orbit, -10_000, {
    minRadius: 1,
    maxRadius: 6,
  });
  assertApprox(orbit.radius, 1, 1e-3);

  applyUsdWorkerOrbitZoomDelta(orbit, 10_000, {
    minRadius: 1,
    maxRadius: 6,
  });
  assertApprox(orbit.radius, 6, 1e-3);
});

test('applyUsdWorkerOrbitZoomDelta supports damped zoom speed for large-scene navigation', () => {
  const baseOrbit = createUsdWorkerOrbitState(
    new THREE.Vector3(0, -25, 5),
    new THREE.Vector3(0, 0, 0),
  );
  const dampedOrbit = createUsdWorkerOrbitState(
    new THREE.Vector3(0, -25, 5),
    new THREE.Vector3(0, 0, 0),
  );
  const originalRadius = baseOrbit.radius;

  applyUsdWorkerOrbitZoomDelta(baseOrbit, -200, {
    zoomSpeed: 0.0015,
    minRadius: 1,
    maxRadius: 100,
  });
  applyUsdWorkerOrbitZoomDelta(dampedOrbit, -200, {
    zoomSpeed: 0.0015 * 0.35,
    minRadius: 1,
    maxRadius: 100,
  });

  assert.ok(
    Math.abs(dampedOrbit.radius - originalRadius) < Math.abs(baseOrbit.radius - originalRadius),
    'expected damped USD worker zoom to change radius less per wheel step',
  );
});

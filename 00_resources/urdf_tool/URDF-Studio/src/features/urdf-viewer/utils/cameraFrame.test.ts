import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  computeCameraFrame,
  computeVisibleBounds,
  createCameraFrameStabilityKey,
  isBoundsVisibleToCamera,
} from './cameraFrame.ts';

function assertVectorClose(actual: THREE.Vector3, expected: THREE.Vector3, epsilon = 1e-6): void {
  assert.ok(actual.distanceTo(expected) <= epsilon, `expected ${actual.toArray()} to be close to ${expected.toArray()}`);
}

function assertBoundsFullyInsideCamera(bounds: THREE.Box3 | null, camera: THREE.Camera): void {
  assert.ok(bounds, 'expected bounds');
  camera.updateMatrixWorld(true);
  const corners = [
    new THREE.Vector3(bounds.min.x, bounds.min.y, bounds.min.z),
    new THREE.Vector3(bounds.min.x, bounds.min.y, bounds.max.z),
    new THREE.Vector3(bounds.min.x, bounds.max.y, bounds.min.z),
    new THREE.Vector3(bounds.min.x, bounds.max.y, bounds.max.z),
    new THREE.Vector3(bounds.max.x, bounds.min.y, bounds.min.z),
    new THREE.Vector3(bounds.max.x, bounds.min.y, bounds.max.z),
    new THREE.Vector3(bounds.max.x, bounds.max.y, bounds.min.z),
    new THREE.Vector3(bounds.max.x, bounds.max.y, bounds.max.z),
  ];

  for (const corner of corners) {
    const projected = corner.clone().project(camera);
    assert.ok(
      projected.x >= -1 && projected.x <= 1 && projected.y >= -1 && projected.y <= 1,
      `expected projected corner ${projected.toArray()} to be inside the camera frame`,
    );
  }
}

test('computeCameraFrame centers on the visible mesh bounds and preserves orbit direction', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(2, 2, 2);

  const currentOrbitTarget = new THREE.Vector3(0, 0, 0);
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 4, 6));
  mesh.position.set(1, -2, 3);
  group.add(mesh);

  const frame = computeCameraFrame(group, camera, currentOrbitTarget);
  assert.ok(frame, 'expected a camera frame result');

  const expectedCenter = new THREE.Box3().setFromObject(mesh).getCenter(new THREE.Vector3());
  assertVectorClose(frame.focusTarget, expectedCenter);

  const initialDirection = camera.position.clone().sub(currentOrbitTarget).normalize();
  const framedDirection = frame.cameraPosition.clone().sub(frame.focusTarget).normalize();
  assertVectorClose(framedDirection, initialDirection);
  assert.ok(frame.cameraPosition.distanceTo(frame.focusTarget) > 0.5);
});

test('computeCameraFrame ignores helper-only objects', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(2, 2, 2);

  const group = new THREE.Group();
  const helperMesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1));
  helperMesh.userData.isHelper = true;
  group.add(helperMesh);

  const frame = computeCameraFrame(group, camera, new THREE.Vector3(0, 0, 0));
  assert.equal(frame, null);
});

test('createCameraFrameStabilityKey is stable for identical bounds', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-1, -2, -3),
    new THREE.Vector3(4, 5, 6),
  );

  assert.equal(
    createCameraFrameStabilityKey(bounds),
    createCameraFrameStabilityKey(bounds.clone()),
  );
  assert.equal(createCameraFrameStabilityKey(null), null);
});

test('isBoundsVisibleToCamera reports whether the framed bounds intersect the current frustum', () => {
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1000);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);

  const visibleBounds = new THREE.Box3(
    new THREE.Vector3(-1, -1, -1),
    new THREE.Vector3(1, 1, 1),
  );
  const hiddenBounds = new THREE.Box3(
    new THREE.Vector3(50, 50, 50),
    new THREE.Vector3(52, 52, 52),
  );

  assert.equal(isBoundsVisibleToCamera(visibleBounds, camera), true);
  assert.equal(isBoundsVisibleToCamera(hiddenBounds, camera), false);
});

test('computeCameraFrame keeps wide bounds visible in a narrow viewport', () => {
  const camera = new THREE.PerspectiveCamera(60, 0.25, 0.1, 1000);
  camera.position.set(0, 4, 1);

  const currentOrbitTarget = new THREE.Vector3(0, 0, 0);
  const group = new THREE.Group();
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(4, 0.5, 0.5));
  group.add(mesh);
  group.updateWorldMatrix(true, true);

  const bounds = computeVisibleBounds(group);
  const frame = computeCameraFrame(group, camera, currentOrbitTarget, bounds);
  assert.ok(frame, 'expected a camera frame result');

  camera.position.copy(frame.cameraPosition);
  camera.lookAt(frame.focusTarget);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);

  assertBoundsFullyInsideCamera(bounds, camera);
});

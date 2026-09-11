import assert from 'node:assert/strict';
import test from 'node:test';

import * as THREE from 'three';

import { resolveMeshPreviewFrame } from './MeshPreview.tsx';

function assertVectorClose(actual: THREE.Vector3, expected: THREE.Vector3, epsilon = 1e-6): void {
  assert.ok(
    actual.distanceTo(expected) <= epsilon,
    `expected ${actual.toArray()} to be close to ${expected.toArray()}`,
  );
}

function assertFinitePositive(value: number, label: string): void {
  assert.ok(Number.isFinite(value) && value > 0, `${label} should be finite and positive`);
}

function assertBoundsFullyInsideCamera(bounds: THREE.Box3, camera: THREE.PerspectiveCamera): void {
  camera.updateProjectionMatrix();
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

  corners.forEach((corner) => {
    const projected = corner.clone().project(camera);
    assert.ok(
      projected.x >= -1 &&
        projected.x <= 1 &&
        projected.y >= -1 &&
        projected.y <= 1 &&
        projected.z >= -1 &&
        projected.z <= 1,
      `expected projected corner ${projected.toArray()} to be inside the preview camera`,
    );
  });
}

test('resolveMeshPreviewFrame recenters an off-origin mesh around its actual bounds center', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(98, -12, 4),
    new THREE.Vector3(104, -6, 10),
  );

  const frame = resolveMeshPreviewFrame(bounds, 16 / 9, 45);
  assert.ok(frame, 'expected preview frame');

  assertVectorClose(frame.center, new THREE.Vector3(101, -9, 7));
  assertVectorClose(frame.contentOffset, new THREE.Vector3(-101, 9, -7));

  const centeredBounds = bounds.clone().translate(frame.contentOffset);
  assertVectorClose(centeredBounds.getCenter(new THREE.Vector3()), new THREE.Vector3(0, 0, 0));
  assertFinitePositive(frame.near, 'near plane');
  assertFinitePositive(frame.far, 'far plane');
  assertFinitePositive(frame.minDistance, 'minimum orbit distance');
  assertFinitePositive(frame.maxDistance, 'maximum orbit distance');
  assert.ok(frame.maxDistance > frame.minDistance, 'orbit distance range should be usable');
});

test('resolveMeshPreviewFrame keeps centered bounds visible in a narrow preview', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-5, -0.25, -0.25),
    new THREE.Vector3(5, 0.25, 0.25),
  );
  const frame = resolveMeshPreviewFrame(bounds, 0.35, 45);
  assert.ok(frame, 'expected preview frame');

  const centeredBounds = bounds.clone().translate(frame.contentOffset);
  const camera = new THREE.PerspectiveCamera(45, 0.35, frame.near, frame.far);
  camera.position.copy(frame.cameraPosition);
  camera.lookAt(0, 0, 0);

  assertBoundsFullyInsideCamera(centeredBounds, camera);
});

test('resolveMeshPreviewFrame leaves enough distance for manual orbit around long meshes', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-0.1, -0.1, -10),
    new THREE.Vector3(0.1, 0.1, 10),
  );
  const frame = resolveMeshPreviewFrame(bounds, 1, 45);
  assert.ok(frame, 'expected preview frame');

  const centeredBounds = bounds.clone().translate(frame.contentOffset);
  const camera = new THREE.PerspectiveCamera(45, 1, frame.near, frame.far);
  camera.position.set(frame.cameraPosition.length(), 0, 0);
  camera.lookAt(0, 0, 0);

  assertBoundsFullyInsideCamera(centeredBounds, camera);
});

test('resolveMeshPreviewFrame falls back to a safe aspect ratio for invalid canvas sizes', () => {
  const bounds = new THREE.Box3(
    new THREE.Vector3(-0.01, -0.01, -0.01),
    new THREE.Vector3(0.01, 0.01, 0.01),
  );

  const frame = resolveMeshPreviewFrame(bounds, Number.NaN, 45);
  assert.ok(frame, 'expected preview frame');
  assertFinitePositive(frame.cameraPosition.length(), 'camera distance');
  assertFinitePositive(frame.far, 'far plane');
  assert.ok(frame.far > frame.near, 'far plane should be beyond near plane');
});

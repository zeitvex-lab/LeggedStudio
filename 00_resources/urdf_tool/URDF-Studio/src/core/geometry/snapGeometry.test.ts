import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';

import {
  computeEdgeIntersectionFrame,
  computeMidPlaneFrame,
  makeFrameFromPointAndNormal,
} from './snapGeometry.ts';

function vec(x: number, y: number, z: number): THREE.Vector3 {
  return new THREE.Vector3(x, y, z);
}

function assertVecNearlyEqual(actual: THREE.Vector3, expected: THREE.Vector3, message?: string) {
  assert.ok(actual.distanceTo(expected) < 1e-6, message ?? `${actual.toArray()} !== ${expected.toArray()}`);
}

function assertNearly(actual: number, expected: number, message?: string) {
  assert.ok(Math.abs(actual - expected) < 1e-6, message ?? `${actual} !== ${expected}`);
}

test('makeFrameFromPointAndNormal builds an orthonormal right-handed frame at the point', () => {
  const frame = makeFrameFromPointAndNormal(vec(1, 2, 3), vec(0, 0, 2));

  assertVecNearlyEqual(new THREE.Vector3().setFromMatrixPosition(frame), vec(1, 2, 3));

  const x = new THREE.Vector3();
  const y = new THREE.Vector3();
  const z = new THREE.Vector3();
  frame.extractBasis(x, y, z);

  assertVecNearlyEqual(z, vec(0, 0, 1), 'Z axis should equal the normalized normal');
  assertNearly(x.length(), 1);
  assertNearly(y.length(), 1);
  assertNearly(x.dot(y), 0);
  assertNearly(x.dot(z), 0);
  assertNearly(y.dot(z), 0);
  assertVecNearlyEqual(new THREE.Vector3().crossVectors(x, y), z, 'frame should be right-handed');
});

test('makeFrameFromPointAndNormal honors the tangent hint', () => {
  const frame = makeFrameFromPointAndNormal(vec(0, 0, 0), vec(0, 0, 1), vec(1, 0, 0));
  const x = new THREE.Vector3();
  const y = new THREE.Vector3();
  const z = new THREE.Vector3();
  frame.extractBasis(x, y, z);
  assertVecNearlyEqual(x, vec(1, 0, 0));
});

test('computeMidPlaneFrame averages parallel planes at their midpoint', () => {
  const frame = computeMidPlaneFrame(
    { point: vec(0, 0, 0), normal: vec(0, 0, 1) },
    { point: vec(0, 0, 2), normal: vec(0, 0, 1) },
  );
  assert.ok(frame);
  assertVecNearlyEqual(new THREE.Vector3().setFromMatrixPosition(frame!), vec(0, 0, 1));

  const z = new THREE.Vector3();
  frame!.extractBasis(new THREE.Vector3(), new THREE.Vector3(), z);
  assertVecNearlyEqual(z, vec(0, 0, 1));
});

test('computeMidPlaneFrame aligns opposing face normals before averaging', () => {
  const frame = computeMidPlaneFrame(
    { point: vec(0, 0, 0), normal: vec(0, 0, 1) },
    { point: vec(0, 0, 2), normal: vec(0, 0, -1) },
  );
  assert.ok(frame);
  assertVecNearlyEqual(new THREE.Vector3().setFromMatrixPosition(frame!), vec(0, 0, 1));

  const z = new THREE.Vector3();
  frame!.extractBasis(new THREE.Vector3(), new THREE.Vector3(), z);
  assertVecNearlyEqual(z, vec(0, 0, 1));
});

test('computeEdgeIntersectionFrame finds the closest point of skew edges', () => {
  const frame = computeEdgeIntersectionFrame(
    { origin: vec(0, 0, 0), direction: vec(1, 0, 0) },
    { origin: vec(0, 0, 2), direction: vec(0, 1, 0) },
  );
  assert.ok(frame);
  assertVecNearlyEqual(new THREE.Vector3().setFromMatrixPosition(frame!), vec(0, 0, 1));

  const x = new THREE.Vector3();
  frame!.extractBasis(x, new THREE.Vector3(), new THREE.Vector3());
  assertVecNearlyEqual(x, vec(1, 0, 0), 'X axis should follow edge A');
});

test('computeEdgeIntersectionFrame returns null for parallel edges', () => {
  const frame = computeEdgeIntersectionFrame(
    { origin: vec(0, 0, 0), direction: vec(1, 0, 0) },
    { origin: vec(0, 1, 0), direction: vec(1, 0, 0) },
  );
  assert.equal(frame, null);
});

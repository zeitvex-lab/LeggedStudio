import test from 'node:test';
import assert from 'node:assert/strict';

import * as THREE from 'three';

import {
  convertMjcfAngle,
  createMuJoCoFromToQuaternion,
  diagonalizeMjcfSymmetric3x3,
  mjcfQuatTupleFromQuaternion,
  normalizeMjcfQuatTuple,
} from './mjcfMath.ts';

function assertCloseArray(
  actual: number[] | null | undefined,
  expected: number[],
  tolerance: number = 1e-6,
): void {
  assert.ok(actual, 'expected array to be defined');
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => {
    assert.ok(
      Math.abs(value - expected[index]!) <= tolerance,
      `index ${index}: expected ${expected[index]}, got ${value}`,
    );
  });
}

function inertiaTensorFromDiagonalization(
  eigenvalues: [number, number, number],
  quat: [number, number, number, number],
): [number, number, number, number, number, number] {
  const [w, x, y, z] = quat;
  const rotation = new THREE.Matrix4().makeRotationFromQuaternion(
    new THREE.Quaternion(x, y, z, w).normalize(),
  );
  const basisX = new THREE.Vector3().setFromMatrixColumn(rotation, 0);
  const basisY = new THREE.Vector3().setFromMatrixColumn(rotation, 1);
  const basisZ = new THREE.Vector3().setFromMatrixColumn(rotation, 2);
  const [ix, iy, iz] = eigenvalues;

  return [
    basisX.x * basisX.x * ix + basisY.x * basisY.x * iy + basisZ.x * basisZ.x * iz,
    basisX.y * basisX.y * ix + basisY.y * basisY.y * iy + basisZ.y * basisZ.y * iz,
    basisX.z * basisX.z * ix + basisY.z * basisY.z * iy + basisZ.z * basisZ.z * iz,
    basisX.x * basisX.y * ix + basisY.x * basisY.y * iy + basisZ.x * basisZ.y * iz,
    basisX.x * basisX.z * ix + basisY.x * basisY.z * iy + basisZ.x * basisZ.z * iz,
    basisX.y * basisX.z * ix + basisY.y * basisY.z * iy + basisZ.y * basisZ.z * iz,
  ];
}

test('converts MJCF angles according to compiler angle units', () => {
  assert.equal(convertMjcfAngle(Math.PI / 3, 'radian'), Math.PI / 3);
  assert.equal(convertMjcfAngle(180, 'degree'), Math.PI);
  assert.equal(convertMjcfAngle(-90, 'degree'), -Math.PI / 2);
});

test('normalizes MJCF quaternion tuples in wxyz order', () => {
  assert.deepEqual(normalizeMjcfQuatTuple(null), null);
  assert.deepEqual(normalizeMjcfQuatTuple([0, 0, 0, 0]), [1, 0, 0, 0]);
  assertCloseArray(normalizeMjcfQuatTuple([1, 1, 0, 0], { precision: 6 }), [
    0.707107,
    0.707107,
    0,
    0,
  ]);
});

test('converts Three.js quaternions to normalized MJCF tuples', () => {
  const quaternion = new THREE.Quaternion(0, Math.SQRT1_2 * 4, 0, Math.SQRT1_2 * 4);

  assertCloseArray(mjcfQuatTupleFromQuaternion(quaternion, { precision: 6 }), [
    0.707107,
    0,
    0.707107,
    0,
  ]);
});

test('creates deterministic MuJoCo fromto quaternions from local negative z', () => {
  assertCloseArray(
    mjcfQuatTupleFromQuaternion(createMuJoCoFromToQuaternion(new THREE.Vector3(1, 0, 0)), {
      precision: 6,
    }),
    [0.707107, 0, -0.707107, 0],
  );
  assertCloseArray(
    mjcfQuatTupleFromQuaternion(createMuJoCoFromToQuaternion(new THREE.Vector3(0, 0, 1)), {
      precision: 6,
    }),
    [0, 1, 0, 0],
  );
});

test('diagonalizes symmetric 3x3 inertia matrices with the existing MJCF ordering', () => {
  const result = diagonalizeMjcfSymmetric3x3(
    [
      [0.085821, 1.276e-5, -0.00016022],
      [1.276e-5, 0.049222, -0.000414],
      [-0.00016022, -0.000414, 0.08626],
    ],
    { precision: 6 },
  );

  assert.ok(result);
  assertCloseArray(result.values, [0.086317, 0.085769, 0.049217], 1e-6);
  assertCloseArray(
    inertiaTensorFromDiagonalization(result.values, result.quat),
    [0.085821, 0.049222, 0.08626, 1.276e-5, -0.00016022, -0.000414],
    1e-4,
  );
});

test('rejects non-finite symmetric 3x3 matrix entries', () => {
  assert.equal(
    diagonalizeMjcfSymmetric3x3([
      [1, 0, 0],
      [0, Number.NaN, 0],
      [0, 0, 1],
    ]),
    null,
  );
});

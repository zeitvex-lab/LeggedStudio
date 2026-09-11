import test from 'node:test';
import assert from 'node:assert/strict';

import {
  composeInertiaTensorFromDerivedValues,
  computeGeometryVolume,
  computeInertialDerivedValues,
  computeLinkDensity,
  scaleInertiaTensorForMassChange,
} from './inertialDerived.ts';

test('computes primitive geometry volume', () => {
  assert.equal(
    computeGeometryVolume({
      type: 'box',
      dimensions: { x: 2, y: 3, z: 4 },
    }),
    24,
  );
});

test('computes density from summed collision primitive volumes', () => {
  const density = computeLinkDensity({
    visual: {
      type: 'none',
      dimensions: { x: 0, y: 0, z: 0 },
    },
    collision: {
      type: 'box',
      dimensions: { x: 1, y: 1, z: 1 },
    },
    collisionBodies: [
      {
        type: 'cylinder',
        dimensions: { x: 0.5, y: 2, z: 0.5 },
      },
    ],
    inertial: {
      mass: 10,
    },
  });

  assert.equal(density.source, 'collision');
  assert.ok(density.value !== null);
  assert.ok(Math.abs(density.value - 10 / (1 + Math.PI * 0.5 * 0.5 * 2)) < 1e-9);
});

test('does not compute density for mesh-based collision geometry', () => {
  const density = computeLinkDensity({
    visual: {
      type: 'box',
      dimensions: { x: 1, y: 1, z: 1 },
    },
    collision: {
      type: 'mesh',
      dimensions: { x: 1, y: 1, z: 1 },
    },
    collisionBodies: [],
    inertial: {
      mass: 10,
    },
  });

  assert.equal(density.source, 'collision');
  assert.equal(density.value, null);
});

test('computes principal moments and principal axes from inertia tensor', () => {
  const derived = computeInertialDerivedValues({
    mass: 5,
    inertia: {
      ixx: 5,
      ixy: 1,
      ixz: 0,
      iyy: 3,
      iyz: 0,
      izz: 2,
    },
  });

  assert.ok(derived);
  assert.deepEqual(
    derived.diagonalInertia.map((value) => Number(value.toFixed(6))),
    [2, 2.585786, 5.414214],
  );

  derived.principalAxes.forEach((axis) => {
    const length = Math.hypot(axis.x, axis.y, axis.z);
    assert.ok(Math.abs(length - 1) < 1e-6);
  });
});

test('recomposes the inertia tensor from derived principal moments and axes', () => {
  const inertial = {
    mass: 5,
    inertia: {
      ixx: 5,
      ixy: 1,
      ixz: 0,
      iyy: 3,
      iyz: 0,
      izz: 2,
    },
  };

  const derived = computeInertialDerivedValues(inertial);
  assert.ok(derived);

  const recomposed = composeInertiaTensorFromDerivedValues(
    derived.diagonalInertia,
    derived.principalAxes,
  );

  assert.ok(Math.abs(recomposed.ixx - inertial.inertia.ixx) < 1e-6);
  assert.ok(Math.abs(recomposed.ixy - inertial.inertia.ixy) < 1e-6);
  assert.ok(Math.abs(recomposed.ixz - inertial.inertia.ixz) < 1e-6);
  assert.ok(Math.abs(recomposed.iyy - inertial.inertia.iyy) < 1e-6);
  assert.ok(Math.abs(recomposed.iyz - inertial.inertia.iyz) < 1e-6);
  assert.ok(Math.abs(recomposed.izz - inertial.inertia.izz) < 1e-6);
});

test('scales inertia tensor linearly when link mass changes under a uniform-density assumption', () => {
  const estimate = scaleInertiaTensorForMassChange(
    {
      mass: 2,
      inertia: {
        ixx: 1,
        ixy: 0.25,
        ixz: 0,
        iyy: 3,
        iyz: -0.5,
        izz: 4,
      },
    },
    5,
  );

  assert.ok(estimate);
  assert.equal(estimate.scale, 2.5);
  assert.deepEqual(estimate.inertia, {
    ixx: 2.5,
    ixy: 0.625,
    ixz: 0,
    iyy: 7.5,
    iyz: -1.25,
    izz: 10,
  });
});

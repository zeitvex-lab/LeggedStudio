import test from 'node:test';
import assert from 'node:assert/strict';

import type { CanonicalMJCFSnapshot } from './mjcfSnapshot.ts';
import { diffCanonicalSnapshots } from './mjcfSnapshot.ts';

function createBaseSnapshot(
  geomOverrides: Partial<CanonicalMJCFSnapshot['geoms'][number]>,
): CanonicalMJCFSnapshot {
  return {
    schema: 'urdf-studio.mjcf-canonical/v1',
    meta: {
      modelName: 'test-model',
      effectiveFile: 'test.xml',
    },
    counts: {
      bodies: 1,
      joints: 0,
      geoms: 1,
      meshes: 0,
      materials: 0,
    },
    bodies: [
      {
        key: 'body',
        name: 'body',
        parentKey: null,
        path: 'body',
        pos: [0, 0, 0],
        quat: [1, 0, 0, 0],
        mass: null,
        inertialPos: null,
        inertialQuat: null,
        inertia: null,
        fullinertia: null,
      },
    ],
    joints: [],
    geoms: [
      {
        key: 'body::geom[0]',
        name: null,
        bodyKey: 'body',
        type: 'capsule',
        size: [0.1, 0.5],
        mesh: null,
        material: null,
        mass: null,
        pos: [0, 0, 0],
        quat: [1, 0, 0, 0],
        rgba: [0.5, 0.5, 0.5, 1],
        group: null,
        contype: null,
        conaffinity: null,
        ...geomOverrides,
      },
    ],
    assets: {
      meshes: [],
      materials: [],
    },
  };
}

function createSnapshotWithBodyMass(bodyMass: number | null): CanonicalMJCFSnapshot {
  const snapshot = createBaseSnapshot({});
  snapshot.bodies = [
    {
      ...snapshot.bodies[0]!,
      mass: bodyMass,
    },
  ];
  return snapshot;
}

function createSnapshotWithJointRange(range: [number, number] | null): CanonicalMJCFSnapshot {
  const snapshot = createBaseSnapshot({});
  snapshot.counts.joints = 1;
  snapshot.joints = [
    {
      key: 'joint',
      name: 'joint',
      parentBodyKey: 'body',
      type: 'hinge',
      axis: [0, 0, 1],
      range,
      pos: [0, 0, 0],
    },
  ];
  return snapshot;
}

function createSnapshotWithJointAxis(axis: [number, number, number] | null): CanonicalMJCFSnapshot {
  const snapshot = createSnapshotWithJointRange(null);
  snapshot.joints = [
    {
      ...snapshot.joints[0]!,
      axis,
    },
  ];
  return snapshot;
}

function createSnapshotWithExplicitBodyInertialAndGeomMass(
  geomMass: number | null,
): CanonicalMJCFSnapshot {
  const snapshot = createBaseSnapshot({
    mass: geomMass,
  });
  snapshot.bodies = [
    {
      ...snapshot.bodies[0]!,
      mass: 12,
      inertialPos: [0, 0, 0],
      inertialQuat: [1, 0, 0, 0],
      inertia: [1, 1, 1],
    },
  ];
  return snapshot;
}

function createSnapshotWithMaterialRgba(
  rgba: [number, number, number, number] | null,
): CanonicalMJCFSnapshot {
  const snapshot = createBaseSnapshot({});
  snapshot.counts.materials = 1;
  snapshot.assets.materials = [
    {
      name: 'white',
      rgba,
      emission: null,
    },
  ];
  return snapshot;
}

test('diffCanonicalSnapshots ignores roll-only quaternion changes for axisymmetric primitives', () => {
  const expected = createBaseSnapshot({
    type: 'capsule',
    quat: [1, 0, 0, 0],
  });
  const actual = createBaseSnapshot({
    type: 'capsule',
    quat: [0.707107, 0, 0, 0.707107],
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_QUAT_MISMATCH'),
    false,
    `expected no capsule quaternion diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots still reports quaternion changes for non-axisymmetric primitives', () => {
  const expected = createBaseSnapshot({
    type: 'box',
    size: [0.1, 0.2, 0.3],
    quat: [1, 0, 0, 0],
  });
  const actual = createBaseSnapshot({
    type: 'box',
    size: [0.1, 0.2, 0.3],
    quat: [0.707107, 0, 0, 0.707107],
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_QUAT_MISMATCH'),
    true,
  );
});

test('diffCanonicalSnapshots treats omitted and zero geom mass as equivalent', () => {
  const expected = createBaseSnapshot({
    mass: null,
  });
  const actual = createBaseSnapshot({
    mass: 0,
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_MASS_MISMATCH'),
    false,
    `expected no geom mass diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots treats normalized joint axes as equivalent', () => {
  const expected = createSnapshotWithJointAxis([0.196116, 0.980581, 0]);
  const actual = createSnapshotWithJointAxis([0.2, 1, 0]);

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'JOINT_AXIS_MISMATCH'),
    false,
    `expected no joint axis diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots ignores geom mass when parent body has explicit inertial data', () => {
  const expected = createSnapshotWithExplicitBodyInertialAndGeomMass(0);
  const actual = createSnapshotWithExplicitBodyInertialAndGeomMass(4);

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_MASS_MISMATCH'),
    false,
    `expected no geom mass diff under explicit inertial, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots tolerates tiny body mass precision differences', () => {
  const expected = createSnapshotWithBodyMass(59.5385);
  const actual = createSnapshotWithBodyMass(59.53854);

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'BODY_MASS_MISMATCH'),
    false,
    `expected no body mass diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots treats omitted material rgba as default white', () => {
  const expected = createSnapshotWithMaterialRgba(null);
  const actual = createSnapshotWithMaterialRgba([1, 1, 1, 1]);

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'MATERIAL_RGBA_MISMATCH'),
    false,
    `expected no material rgba diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots tolerates tiny joint range precision differences', () => {
  const expected = createSnapshotWithJointRange([-12.2064, 12.9263]);
  const actual = createSnapshotWithJointRange([-12.206419, 12.926322]);

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'JOINT_RANGE_MISMATCH'),
    false,
    `expected no joint range diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots treats extra sphere size axes as non-semantic', () => {
  const expected = createBaseSnapshot({
    type: 'sphere',
    size: [0.057],
  });
  const actual = createBaseSnapshot({
    type: 'sphere',
    size: [0.057, 0.04675, 0.057],
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_SIZE_MISMATCH'),
    false,
    `expected no sphere size diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots treats extra cylinder size axes as non-semantic', () => {
  const expected = createBaseSnapshot({
    type: 'cylinder',
    size: [0.02, 0.04],
  });
  const actual = createBaseSnapshot({
    type: 'cylinder',
    size: [0.02, 0.04, 0.04],
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_SIZE_MISMATCH'),
    false,
    `expected no cylinder size diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

test('diffCanonicalSnapshots treats extra capsule size axes as non-semantic', () => {
  const expected = createBaseSnapshot({
    type: 'capsule',
    size: [0.009, 0.012],
  });
  const actual = createBaseSnapshot({
    type: 'capsule',
    size: [0.009, 0.012, 0.008],
  });

  const diffs = diffCanonicalSnapshots(expected, actual);

  assert.equal(
    diffs.some((diff) => diff.type === 'GEOM_SIZE_MISMATCH'),
    false,
    `expected no capsule size diff, got ${JSON.stringify(diffs, null, 2)}`,
  );
});

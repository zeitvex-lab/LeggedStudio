import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { DEFAULT_LINK } from '@/types';
import {
  buildUsdLinkDynamicsRecordMap,
  composeUsdMeshOverrideWorldMatrix,
  composeUsdMeshOverrideWorldMatrixFromBaseLocal,
  deriveUsdMeshBaseLocalMatrix,
  isUsdRuntimeGeometryVisible,
  resolveUsdRuntimeGeometry,
  resolveUsdVisualColorOverride,
  resolveUsdVisualColorOverrideForMesh,
} from './usdRuntimeLinkOverrides.ts';

test('resolves collision geometry by runtime object index', () => {
  const link = {
    ...DEFAULT_LINK,
    collision: {
      ...DEFAULT_LINK.collision,
      dimensions: { x: 1, y: 2, z: 3 },
    },
    collisionBodies: [
      {
        ...DEFAULT_LINK.collision,
        dimensions: { x: 4, y: 5, z: 6 },
      },
    ],
  };

  assert.deepEqual(resolveUsdRuntimeGeometry(link, 'collision', 1)?.dimensions, {
    x: 4,
    y: 5,
    z: 6,
  });
});

test('treats collision meshes without a runtime object index as absent', () => {
  const link = {
    ...DEFAULT_LINK,
    collision: {
      ...DEFAULT_LINK.collision,
      dimensions: { x: 1, y: 2, z: 3 },
    },
  };

  assert.equal(resolveUsdRuntimeGeometry(link, 'collision'), undefined);
  assert.equal(
    isUsdRuntimeGeometryVisible({
      link,
      role: 'collision',
      objectIndex: undefined,
      showVisual: false,
      showCollision: true,
    }),
    false,
  );
});

test('applies geometry translation in link-local space when composing USD mesh overrides', () => {
  const linkWorldMatrix = new THREE.Matrix4().makeRotationZ(Math.PI / 2);
  linkWorldMatrix.setPosition(new THREE.Vector3(2, 0, 0));

  const authoredWorldMatrix = new THREE.Matrix4().makeTranslation(3, 0, 0);
  const composed = composeUsdMeshOverrideWorldMatrix({
    authoredWorldMatrix,
    geometry: {
      ...DEFAULT_LINK.visual,
      origin: {
        xyz: { x: 1, y: 0, z: 0 },
        rpy: { r: 0, p: 0, y: 0 },
      },
      dimensions: { x: 1, y: 1, z: 1 },
    },
    linkWorldMatrix,
  });

  const position = new THREE.Vector3();
  const rotation = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  composed.decompose(position, rotation, scale);

  assert.ok(Math.abs(position.x - 3) < 1e-6);
  assert.ok(Math.abs(position.y - 1) < 1e-6);
  assert.ok(Math.abs(position.z) < 1e-6);
});

test('reuses a stable authored local matrix so repeated USD overrides do not drift', () => {
  const linkWorldMatrix = new THREE.Matrix4().makeRotationZ(Math.PI / 2);
  linkWorldMatrix.setPosition(new THREE.Vector3(2, 0, 0));

  const authoredWorldMatrix = new THREE.Matrix4().makeTranslation(3, 0, 0);
  const geometry = {
    ...DEFAULT_LINK.visual,
    origin: {
      xyz: { x: 1, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
    dimensions: { x: 1, y: 1, z: 1 },
  };

  const stableBaseLocalMatrix = linkWorldMatrix
    .clone()
    .invert()
    .multiply(authoredWorldMatrix.clone());
  const first = composeUsdMeshOverrideWorldMatrixFromBaseLocal({
    baseLocalMatrix: stableBaseLocalMatrix,
    geometry,
    linkWorldMatrix,
  });
  const second = composeUsdMeshOverrideWorldMatrixFromBaseLocal({
    baseLocalMatrix: stableBaseLocalMatrix,
    geometry,
    linkWorldMatrix,
  });
  const drifted = composeUsdMeshOverrideWorldMatrix({
    authoredWorldMatrix: first,
    geometry,
    linkWorldMatrix,
  });

  const firstPosition = new THREE.Vector3();
  const secondPosition = new THREE.Vector3();
  const driftedPosition = new THREE.Vector3();
  first.decompose(firstPosition, new THREE.Quaternion(), new THREE.Vector3());
  second.decompose(secondPosition, new THREE.Quaternion(), new THREE.Vector3());
  drifted.decompose(driftedPosition, new THREE.Quaternion(), new THREE.Vector3());

  assert.ok(firstPosition.distanceTo(secondPosition) < 1e-6);
  assert.ok(firstPosition.distanceTo(driftedPosition) > 0.5);
});

test('deriveUsdMeshBaseLocalMatrix preserves the authored world transform when the current geometry matches the hydrated baseline', () => {
  const linkWorldMatrix = new THREE.Matrix4().makeRotationZ(Math.PI / 3);
  linkWorldMatrix.setPosition(new THREE.Vector3(1.5, -0.5, 0.25));

  const baselineGeometry = {
    ...DEFAULT_LINK.visual,
    origin: {
      xyz: { x: 0.4, y: -0.2, z: 0.8 },
      rpy: { r: 0.1, p: -0.15, y: 0.05 },
    },
    dimensions: { x: 1.2, y: 0.9, z: 1.1 },
  };

  const authoredWorldMatrix = composeUsdMeshOverrideWorldMatrix({
    authoredWorldMatrix: new THREE.Matrix4().compose(
      new THREE.Vector3(3, 1, -0.5),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.2, 0.15, 0.35)),
      new THREE.Vector3(1, 1, 1),
    ),
    geometry: baselineGeometry,
    linkWorldMatrix,
  });

  const baseLocalMatrix = deriveUsdMeshBaseLocalMatrix({
    authoredWorldMatrix,
    baselineGeometry,
    linkWorldMatrix,
  });

  const recomposedWorldMatrix = composeUsdMeshOverrideWorldMatrixFromBaseLocal({
    baseLocalMatrix,
    geometry: baselineGeometry,
    linkWorldMatrix,
  });

  const recomposedPosition = new THREE.Vector3();
  const authoredPosition = new THREE.Vector3();
  recomposedWorldMatrix.decompose(recomposedPosition, new THREE.Quaternion(), new THREE.Vector3());
  authoredWorldMatrix.decompose(authoredPosition, new THREE.Quaternion(), new THREE.Vector3());

  assert.ok(recomposedPosition.distanceTo(authoredPosition) < 1e-6);
});

test('only applies a USD visual color override when the panel changed away from the baseline snapshot', () => {
  assert.equal(
    resolveUsdVisualColorOverride(
      { ...DEFAULT_LINK.visual, color: '#ff0000' },
      { ...DEFAULT_LINK.visual, color: '#64748b' },
    ),
    '#ff0000',
  );

  assert.equal(
    resolveUsdVisualColorOverride(
      { ...DEFAULT_LINK.visual, color: '#64748b' },
      { ...DEFAULT_LINK.visual, color: '#64748b' },
    ),
    null,
  );
});

test('does not return a USD visual color override for multi-material visuals', () => {
  assert.equal(
    resolveUsdVisualColorOverride(
      {
        ...DEFAULT_LINK.visual,
        color: '#e0e0e0',
        authoredMaterials: [
          { name: 'body', color: '#d3d7d3' },
          { name: 'accent_dark', color: '#000000' },
        ],
      },
      {
        ...DEFAULT_LINK.visual,
        color: '#64748b',
        authoredMaterials: [
          { name: 'body', color: '#d3d7d3' },
          { name: 'accent_dark', color: '#000000' },
        ],
      },
    ),
    null,
  );
});

test('does not apply a USD visual color override to multi-slot meshes', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.addGroup(0, 3, 0);
  geometry.addGroup(3, 3, 1);
  const mesh = new THREE.Mesh(geometry, [
    new THREE.MeshStandardMaterial({ color: '#d3d7d3' }),
    new THREE.MeshStandardMaterial({ color: '#000000' }),
  ]);

  assert.equal(
    resolveUsdVisualColorOverrideForMesh(
      mesh,
      {
        ...DEFAULT_LINK.visual,
        color: '#e0e0e0',
        authoredMaterials: [
          { name: 'body', color: '#d3d7d3' },
          { name: 'accent_dark', color: '#000000' },
        ],
      },
      {
        ...DEFAULT_LINK.visual,
        color: '#64748b',
        authoredMaterials: [
          { name: 'body', color: '#d3d7d3' },
          { name: 'accent_dark', color: '#000000' },
        ],
      },
    ),
    null,
  );
});

test('derives USD runtime visibility from link and geometry flags', () => {
  const link = {
    ...DEFAULT_LINK,
    visible: false,
    visual: {
      ...DEFAULT_LINK.visual,
      visible: true,
    },
  };

  assert.equal(
    isUsdRuntimeGeometryVisible({
      link,
      role: 'visual',
      showVisual: true,
      showCollision: false,
    }),
    false,
  );

  assert.equal(
    isUsdRuntimeGeometryVisible({
      link: {
        ...DEFAULT_LINK,
        visible: false,
        collision: {
          ...DEFAULT_LINK.collision,
          visible: true,
        },
      },
      role: 'collision',
      objectIndex: 0,
      showVisual: false,
      showCollision: true,
    }),
    false,
  );
});

test('can keep USD runtime collisions visible in collision-only mode when link visibility is off', () => {
  assert.equal(
    isUsdRuntimeGeometryVisible({
      link: {
        ...DEFAULT_LINK,
        visible: false,
        collision: {
          ...DEFAULT_LINK.collision,
          visible: true,
        },
      },
      role: 'collision',
      objectIndex: 0,
      showVisual: false,
      showCollision: true,
      respectLinkVisibility: false,
    }),
    true,
  );

  assert.equal(
    isUsdRuntimeGeometryVisible({
      link: {
        ...DEFAULT_LINK,
        visible: false,
        collision: {
          ...DEFAULT_LINK.collision,
          visible: false,
        },
      },
      role: 'collision',
      objectIndex: 0,
      showVisual: false,
      showCollision: true,
      respectLinkVisibility: false,
    }),
    false,
  );
});

test('builds link dynamics records from the current robot links', () => {
  const resolution = {
    robotData: {
      name: 'robot',
      links: {
        base_link: {
          ...DEFAULT_LINK,
          id: 'base_link',
          name: 'base_link',
        },
      },
      joints: {},
      rootLinkId: 'base_link',
    },
    stageSourcePath: '/robot.usd',
    linkIdByPath: {
      '/robot/base_link': 'base_link',
    },
    linkPathById: {
      base_link: '/robot/base_link',
    },
    jointPathById: {},
    childLinkPathByJointId: {},
    parentLinkPathByJointId: {},
  };

  const records = buildUsdLinkDynamicsRecordMap({
    resolution,
    robotLinks: {
      base_link: {
        ...DEFAULT_LINK,
        id: 'base_link',
        name: 'base_link',
        inertial: {
          ...DEFAULT_LINK.inertial,
          mass: 5,
          origin: {
            xyz: { x: 0.1, y: 0.2, z: 0.3 },
            rpy: { r: 0, p: 0, y: Math.PI / 2 },
          },
          inertia: {
            ixx: 1,
            ixy: 0,
            ixz: 0,
            iyy: 2,
            iyz: 0,
            izz: 3,
          },
        },
      },
    },
  });

  const record = records.get('/robot/base_link');
  assert.ok(record);
  assert.equal(record?.mass, 5);
  assert.deepEqual(record?.centerOfMassLocal.toArray(), [0.1, 0.2, 0.3]);
  assert.deepEqual(record?.diagonalInertia?.toArray(), [1, 2, 3]);
  assert.ok(
    record?.principalAxesLocal.angleTo(
      new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, Math.PI / 2, 'ZYX')),
    ) < 1e-6,
  );
});

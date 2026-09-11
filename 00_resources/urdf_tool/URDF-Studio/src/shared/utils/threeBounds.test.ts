import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  alignObjectLowestPointToZ,
  computeVisibleMeshBounds,
  getLowestMeshZ,
} from './threeBounds.ts';

function createBoxMesh(size: number, position: [number, number, number]) {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(size, size, size),
    new THREE.MeshBasicMaterial(),
  );
  mesh.position.set(...position);
  return mesh;
}

test('computeVisibleMeshBounds skips helper and infrastructure meshes', () => {
  const root = new THREE.Group();

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  robotMesh.name = 'RobotMesh';
  root.add(robotMesh);

  const helperMesh = createBoxMesh(40, [100, 0, 0]);
  helperMesh.userData.isHelper = true;
  helperMesh.name = 'ReferenceGrid';
  root.add(helperMesh);

  const excludedMesh = createBoxMesh(30, [0, 100, 0]);
  excludedMesh.userData.excludeFromSceneBounds = true;
  excludedMesh.name = 'GroundShadowPlane';
  root.add(excludedMesh);

  const bounds = computeVisibleMeshBounds(root);
  assert.ok(bounds);
  assert.deepEqual(
    bounds.min.toArray().map((value) => Number(value.toFixed(6))),
    [-1, -1, -1],
  );
  assert.deepEqual(
    bounds.max.toArray().map((value) => Number(value.toFixed(6))),
    [1, 1, 1],
  );
});

test('computeVisibleMeshBounds excludes invisible descendants by default', () => {
  const root = new THREE.Group();
  const visibleMesh = createBoxMesh(2, [0, 0, 0]);
  const hiddenParent = new THREE.Group();
  hiddenParent.visible = false;
  const hiddenMesh = createBoxMesh(20, [50, 0, 0]);
  hiddenParent.add(hiddenMesh);
  root.add(visibleMesh, hiddenParent);

  const bounds = computeVisibleMeshBounds(root);
  assert.ok(bounds);
  assert.equal(bounds.max.x, 1);
});

test('computeVisibleMeshBounds can include invisible descendants when requested', () => {
  const root = new THREE.Group();
  const visibleMesh = createBoxMesh(2, [0, 0, 0]);
  const hiddenParent = new THREE.Group();
  hiddenParent.visible = false;
  const hiddenMesh = createBoxMesh(20, [50, 0, 0]);
  hiddenParent.add(hiddenMesh);
  root.add(visibleMesh, hiddenParent);

  const bounds = computeVisibleMeshBounds(root, { includeInvisible: true });
  assert.ok(bounds);
  assert.equal(bounds.max.x, 60);
});

test('computeVisibleMeshBounds can include ground plane helpers for camera clipping', () => {
  const root = new THREE.Group();

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  root.add(robotMesh);

  const gridMesh = createBoxMesh(20, [0, 0, 0]);
  gridMesh.userData.isHelper = true;
  gridMesh.name = 'ReferenceGrid';
  root.add(gridMesh);

  const shadowMesh = createBoxMesh(24, [0, 0, 0]);
  shadowMesh.userData.excludeFromSceneBounds = true;
  shadowMesh.name = 'GroundShadowPlane';
  root.add(shadowMesh);

  const unrelatedHelper = createBoxMesh(40, [100, 0, 0]);
  unrelatedHelper.userData.isHelper = true;
  unrelatedHelper.name = 'WorldOriginAxes';
  root.add(unrelatedHelper);

  const bounds = computeVisibleMeshBounds(root, { includeGroundPlaneHelpers: true });
  assert.ok(bounds);
  assert.deepEqual(
    bounds.min.toArray().map((value) => Number(value.toFixed(6))),
    [-12, -12, -12],
  );
  assert.deepEqual(
    bounds.max.toArray().map((value) => Number(value.toFixed(6))),
    [12, 12, 12],
  );
});

test('computeVisibleMeshBounds skips meshes nested under helper wrappers', () => {
  const root = new THREE.Group();

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  root.add(robotMesh);

  const helperGroup = new THREE.Group();
  helperGroup.userData.isHelper = true;
  const nestedHelperMesh = createBoxMesh(40, [100, 0, 0]);
  helperGroup.add(nestedHelperMesh);
  root.add(helperGroup);

  const bounds = computeVisibleMeshBounds(root);
  assert.ok(bounds);
  assert.deepEqual(
    bounds.min.toArray().map((value) => Number(value.toFixed(6))),
    [-1, -1, -1],
  );
  assert.deepEqual(
    bounds.max.toArray().map((value) => Number(value.toFixed(6))),
    [1, 1, 1],
  );
});

test('ground alignment ignores helper descendant meshes', () => {
  const root = new THREE.Group();

  const robotMesh = createBoxMesh(2, [0, 0, 5]);
  root.add(robotMesh);

  const helperGroup = new THREE.Group();
  helperGroup.userData.isHelper = true;
  const nestedHelperMesh = createBoxMesh(20, [0, 0, -50]);
  helperGroup.add(nestedHelperMesh);
  root.add(helperGroup);

  const lowestZ = getLowestMeshZ(root, { includeVisual: true, includeCollision: false });
  assert.equal(lowestZ, 4);

  const alignedZ = alignObjectLowestPointToZ(root, 0, {
    includeVisual: true,
    includeCollision: false,
  });
  assert.equal(alignedZ, 0);
  assert.equal(Number(root.position.z.toFixed(6)), -4);
});

test('ground alignment keeps URDF runtime roots that use __-prefixed synthetic names', () => {
  const root = new THREE.Group();
  root.name = '__workspace_world__::component::comp_demo';
  (root as THREE.Group & { isURDFJoint?: boolean }).isURDFJoint = true;

  const robotMesh = createBoxMesh(2, [0, 0, 5]);
  robotMesh.userData.isVisualMesh = true;
  root.add(robotMesh);

  const lowestZ = getLowestMeshZ(root, { includeVisual: true, includeCollision: false });
  assert.equal(lowestZ, 4);

  const alignedZ = alignObjectLowestPointToZ(root, 0, {
    includeVisual: true,
    includeCollision: false,
  });
  assert.equal(alignedZ, 0);
  assert.equal(Number(root.position.z.toFixed(6)), -4);
});

test('getLowestMeshZ resolves nested roots against current ancestor world transforms', () => {
  const parent = new THREE.Group();
  parent.position.z = 5;
  const root = new THREE.Group();
  parent.add(root);

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  robotMesh.userData.isVisualMesh = true;
  root.add(robotMesh);

  const lowestZ = getLowestMeshZ(root, { includeVisual: true, includeCollision: false });
  assert.equal(lowestZ, 4);
});

test('alignObjectLowestPointToZ grounds nested roots using ancestor-aware world matrices', () => {
  const parent = new THREE.Group();
  parent.position.z = 5;
  const root = new THREE.Group();
  parent.add(root);

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  robotMesh.userData.isVisualMesh = true;
  root.add(robotMesh);

  const alignedZ = alignObjectLowestPointToZ(root, 0, {
    includeVisual: true,
    includeCollision: false,
  });

  assert.equal(alignedZ, 0);
  assert.equal(Number(root.position.z.toFixed(6)), -4);
  assert.equal(getLowestMeshZ(root, { includeVisual: true, includeCollision: false }), 0);
});

test('alignObjectLowestPointToZ handles rotated parents without leaving a ground gap', () => {
  const parent = new THREE.Group();
  parent.rotation.x = Math.PI / 6;
  const root = new THREE.Group();
  parent.add(root);

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  robotMesh.userData.isVisualMesh = true;
  root.add(robotMesh);

  const alignedZ = alignObjectLowestPointToZ(root, 0, {
    includeVisual: true,
    includeCollision: false,
  });

  assert.equal(alignedZ, 0);
  assert.ok(
    Math.abs(getLowestMeshZ(root, { includeVisual: true, includeCollision: false }) ?? Infinity) <
      1e-9,
  );
});

test('alignObjectLowestPointToZ handles scaled parents when converting world delta to local space', () => {
  const parent = new THREE.Group();
  parent.scale.set(1, 1, 2);
  parent.position.z = 3;
  const root = new THREE.Group();
  parent.add(root);

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  robotMesh.userData.isVisualMesh = true;
  root.add(robotMesh);

  const alignedZ = alignObjectLowestPointToZ(root, 0, {
    includeVisual: true,
    includeCollision: false,
  });

  assert.equal(alignedZ, 0);
  assert.equal(Number(root.position.z.toFixed(6)), -0.5);
  assert.ok(
    Math.abs(getLowestMeshZ(root, { includeVisual: true, includeCollision: false }) ?? Infinity) <
      1e-9,
  );
});

test('computeVisibleMeshBounds uses ancestor transforms when measuring nested roots', () => {
  const parent = new THREE.Group();
  parent.position.set(1, -2, 5);
  const root = new THREE.Group();
  parent.add(root);

  const robotMesh = createBoxMesh(2, [0, 0, 0]);
  root.add(robotMesh);

  const bounds = computeVisibleMeshBounds(root);
  assert.ok(bounds);
  assert.deepEqual(
    bounds.min.toArray().map((value) => Number(value.toFixed(6))),
    [0, -3, 4],
  );
  assert.deepEqual(
    bounds.max.toArray().map((value) => Number(value.toFixed(6))),
    [2, -1, 6],
  );
});

import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { removeHandlesByNames } from './displayPatchShared.ts';

test('removeHandlesByNames disposes removed handle resources when they are not shared', () => {
  const group = new THREE.Group();

  let geometryDisposeCalls = 0;
  let materialDisposeCalls = 0;

  const geometry = new THREE.BoxGeometry(1, 1, 1);
  geometry.dispose = () => {
    geometryDisposeCalls += 1;
  };

  const material = new THREE.MeshBasicMaterial({ color: 0xffffff });
  material.dispose = () => {
    materialDisposeCalls += 1;
  };

  const removable = new THREE.Mesh(geometry, material);
  removable.name = 'X';
  group.add(removable);

  removeHandlesByNames(group, new Set(['X']));

  assert.equal(group.children.includes(removable), false);
  assert.equal(geometryDisposeCalls, 1);
  assert.equal(materialDisposeCalls, 1);
});

test('removeHandlesByNames keeps shared resources alive for surviving handles', () => {
  const group = new THREE.Group();

  let geometryDisposeCalls = 0;
  let materialDisposeCalls = 0;

  const sharedGeometry = new THREE.BoxGeometry(1, 1, 1);
  sharedGeometry.dispose = () => {
    geometryDisposeCalls += 1;
  };

  const sharedMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });
  sharedMaterial.dispose = () => {
    materialDisposeCalls += 1;
  };

  const removable = new THREE.Mesh(sharedGeometry, sharedMaterial);
  removable.name = 'XYZE';
  const surviving = new THREE.Mesh(sharedGeometry, sharedMaterial);
  surviving.name = 'X';
  group.add(removable);
  group.add(surviving);

  removeHandlesByNames(group, new Set(['XYZE']));

  assert.equal(group.children.includes(removable), false);
  assert.equal(group.children.includes(surviving), true);
  assert.equal(geometryDisposeCalls, 0);
  assert.equal(materialDisposeCalls, 0);
});

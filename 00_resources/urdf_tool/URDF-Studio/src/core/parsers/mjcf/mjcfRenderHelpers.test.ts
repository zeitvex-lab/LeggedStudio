import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { applyRgbaToMesh } from './mjcfRenderHelpers';

function createIndexedTriangleMesh(triangleCount: number): THREE.Mesh {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
    ], 3),
  );

  const index = new Uint32Array(triangleCount * 3);
  for (let i = 0; i < index.length; i += 3) {
    index[i] = 0;
    index[i + 1] = 1;
    index[i + 2] = 2;
  }

  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  return new THREE.Mesh(geometry, new THREE.MeshPhongMaterial({ color: 0x808080 }));
}

test('applyRgbaToMesh keeps G1-class MJCF meshes in the shared shadow pass', () => {
  const mesh = createIndexedTriangleMesh(51410);

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  applyRgbaToMesh(mesh, [0.5, 0.5, 0.5, 1]);

  assert.equal(mesh.material instanceof THREE.MeshStandardMaterial, true);
  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
});

test('applyRgbaToMesh keeps extremely dense MJCF meshes in the shadow pass', () => {
  const mesh = createIndexedTriangleMesh(70000);

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  applyRgbaToMesh(mesh, [0.5, 0.5, 0.5, 1]);

  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
});

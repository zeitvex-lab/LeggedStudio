import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { prepareUsdVisualMesh } from './usdVisualRendering';

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
  return new THREE.Mesh(geometry, new THREE.MeshPhysicalMaterial({ color: '#808080' }));
}

test('prepareUsdVisualMesh enables the same shadow participation as the URDF viewer path for G1-class meshes', () => {
  const mesh = createIndexedTriangleMesh(51410);

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  prepareUsdVisualMesh(mesh);

  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
  assert.equal(mesh.userData.__usdVisualMeshPrepared, true);
});

test('prepareUsdVisualMesh keeps Go2 USDA base meshes in the shadow pass', () => {
  const mesh = createIndexedTriangleMesh(77928);

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  prepareUsdVisualMesh(mesh);

  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
  assert.equal(mesh.userData.__usdVisualMeshPrepared, true);
});

test('prepareUsdVisualMesh skips extremely dense USD visual meshes', () => {
  const mesh = createIndexedTriangleMesh(86240);

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  prepareUsdVisualMesh(mesh);

  assert.equal(mesh.castShadow, false);
  assert.equal(mesh.receiveShadow, false);
  assert.equal(mesh.userData.__usdVisualMeshPrepared, true);
});

test('prepareUsdVisualMesh re-applies the normalized shadow flags on repeated calls', () => {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshPhysicalMaterial({ color: '#ff6c0a' }),
  );

  mesh.castShadow = false;
  mesh.receiveShadow = false;

  prepareUsdVisualMesh(mesh);

  assert.equal(mesh.castShadow, true);
  assert.equal(mesh.receiveShadow, true);
  assert.equal(mesh.userData.__usdVisualMeshPrepared, true);
});

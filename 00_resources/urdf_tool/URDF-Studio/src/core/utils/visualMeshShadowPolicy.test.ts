import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  applyVisualMeshShadowPolicy,
  applyVisualMeshShadowPolicyToObject,
  getVisualMeshTriangleCount,
  shouldVisualMeshParticipateInShadows,
} from './visualMeshShadowPolicy';

function createIndexedTriangleMesh(triangleCount: number): THREE.Mesh {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );

  const index = new Uint32Array(triangleCount * 3);
  for (let i = 0; i < index.length; i += 3) {
    index[i] = 0;
    index[i + 1] = 1;
    index[i + 2] = 2;
  }

  geometry.setIndex(new THREE.BufferAttribute(index, 1));
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0x999999 }));
}

test('shared visual mesh shadow policy keeps G1-class meshes in the shadow pass', () => {
  const g1ScaleMesh = createIndexedTriangleMesh(51410);

  assert.equal(getVisualMeshTriangleCount(g1ScaleMesh), 51410);
  assert.equal(shouldVisualMeshParticipateInShadows(g1ScaleMesh), true);

  applyVisualMeshShadowPolicy(g1ScaleMesh);

  assert.equal(g1ScaleMesh.castShadow, true);
  assert.equal(g1ScaleMesh.receiveShadow, true);
});

test('shared visual mesh shadow policy keeps Go2 ROS base meshes in the shadow pass', () => {
  const go2BaseMesh = createIndexedTriangleMesh(77928);

  assert.equal(getVisualMeshTriangleCount(go2BaseMesh), 77928);
  assert.equal(shouldVisualMeshParticipateInShadows(go2BaseMesh), true);

  applyVisualMeshShadowPolicy(go2BaseMesh);

  assert.equal(go2BaseMesh.castShadow, true);
  assert.equal(go2BaseMesh.receiveShadow, true);
});

test('shared visual mesh shadow policy skips extremely dense meshes', () => {
  const hugeMesh = createIndexedTriangleMesh(86240);

  assert.equal(getVisualMeshTriangleCount(hugeMesh), 86240);
  assert.equal(shouldVisualMeshParticipateInShadows(hugeMesh), false);

  applyVisualMeshShadowPolicy(hugeMesh);

  assert.equal(hugeMesh.castShadow, false);
  assert.equal(hugeMesh.receiveShadow, false);
});

test('shared visual mesh shadow policy traverses object trees and skips non-mesh helpers', () => {
  const root = new THREE.Group();
  const meshA = createIndexedTriangleMesh(12);
  const meshB = createIndexedTriangleMesh(6);
  const helper = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(1, 0, 0),
    ]),
    new THREE.LineBasicMaterial({ color: 0xffffff }),
  );

  meshA.castShadow = false;
  meshA.receiveShadow = false;
  meshB.castShadow = false;
  meshB.receiveShadow = false;

  root.add(meshA);
  root.add(helper);
  helper.add(meshB);

  assert.equal(applyVisualMeshShadowPolicyToObject(root), 2);
  assert.equal(meshA.castShadow, true);
  assert.equal(meshA.receiveShadow, true);
  assert.equal(meshB.castShadow, true);
  assert.equal(meshB.receiveShadow, true);
  assert.equal((helper as THREE.Line).castShadow, false);
  assert.equal((helper as THREE.Line).receiveShadow, false);
});

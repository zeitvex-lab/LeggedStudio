import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  alignUsdSceneRootToGround,
  resolveUsdGroundAlignmentBaseline,
} from './usdGroundAlignment.ts';

function createVisualBox(centerZ: number) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  mesh.userData.isVisualMesh = true;
  mesh.position.z = centerZ;
  return mesh;
}

test('alignUsdSceneRootToGround recomputes the current lowest point after pose changes', () => {
  const root = new THREE.Group();
  const jointGroup = new THREE.Group();
  const mesh = createVisualBox(2);
  jointGroup.add(mesh);
  root.add(jointGroup);

  assert.equal(resolveUsdGroundAlignmentBaseline(root), 1.5);
  assert.equal(alignUsdSceneRootToGround(root, 0), true);
  assert.equal(Number(root.position.z.toFixed(6)), -1.5);

  jointGroup.position.z = -1;
  root.updateMatrixWorld(true);

  assert.equal(resolveUsdGroundAlignmentBaseline(root), -1);
  assert.equal(alignUsdSceneRootToGround(root, 0), true);
  assert.equal(Number(root.position.z.toFixed(6)), -0.5);

  mesh.geometry.dispose();
  (mesh.material as THREE.Material).dispose();
});

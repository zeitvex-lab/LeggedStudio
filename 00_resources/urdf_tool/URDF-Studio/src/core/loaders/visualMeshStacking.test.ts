import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { isCoplanarOffsetMaterial } from './index.ts';
import { stackCoincidentVisualRoots } from './visualMeshStacking.ts';

function createVisualRoot(
  name: string,
  meshSize: [number, number, number],
  meshOffset: [number, number, number] = [0, 0, 0],
): THREE.Group {
  const root = new THREE.Group();
  root.name = name;

  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(...meshSize),
    new THREE.MeshStandardMaterial({ name }),
  );
  mesh.position.set(...meshOffset);
  root.add(mesh);

  return root;
}

test('stackCoincidentVisualRoots does not stack distinct mesh parts that only share a root transform', () => {
  const left = createVisualRoot('left_part', [0.4, 0.2, 0.2], [-1, 0, 0]);
  const right = createVisualRoot('right_part', [0.4, 0.2, 0.2], [1, 0, 0]);

  stackCoincidentVisualRoots([
    { root: left, stableId: 'left' },
    { root: right, stableId: 'right' },
  ], { space: 'world' });

  const leftMesh = left.children[0] as THREE.Mesh;
  const rightMesh = right.children[0] as THREE.Mesh;

  assert.equal(left.userData.visualStackIndex, 0);
  assert.equal(right.userData.visualStackIndex, 0);
  assert.equal(leftMesh.renderOrder, 0);
  assert.equal(rightMesh.renderOrder, 0);
  assert.equal(isCoplanarOffsetMaterial(leftMesh.material as THREE.Material), false);
  assert.equal(isCoplanarOffsetMaterial(rightMesh.material as THREE.Material), false);
});

test('stackCoincidentVisualRoots does not stack overlapping internals whose bounds ratios are not shell-like', () => {
  const outerBody = createVisualRoot('outer_body', [1.2, 0.28, 0.56]);
  const innerCore = createVisualRoot('inner_core', [0.26, 1.04, 0.98]);

  stackCoincidentVisualRoots([
    { root: outerBody, stableId: 'outer' },
    { root: innerCore, stableId: 'inner' },
  ], { space: 'world' });

  const outerMesh = outerBody.children[0] as THREE.Mesh;
  const innerMesh = innerCore.children[0] as THREE.Mesh;

  assert.equal(outerBody.userData.visualStackIndex, 0);
  assert.equal(innerCore.userData.visualStackIndex, 0);
  assert.equal(outerMesh.renderOrder, 0);
  assert.equal(innerMesh.renderOrder, 0);
  assert.equal(isCoplanarOffsetMaterial(outerMesh.material as THREE.Material), false);
  assert.equal(isCoplanarOffsetMaterial(innerMesh.material as THREE.Material), false);
});

test('stackCoincidentVisualRoots still stacks overlapping shell layers across fixed-parent world transforms', () => {
  const parentA = new THREE.Group();
  const parentB = new THREE.Group();
  parentB.position.set(0.4, -0.2, 0.1);

  const inner = createVisualRoot('inner_shell', [1, 1, 1]);
  const outer = createVisualRoot('outer_shell', [1.04, 1.04, 1.04]);
  outer.position.set(-0.4, 0.2, -0.1);

  parentA.add(inner);
  parentB.add(outer);
  parentA.updateMatrixWorld(true);
  parentB.updateMatrixWorld(true);

  stackCoincidentVisualRoots([
    { root: inner, stableId: 'inner' },
    { root: outer, stableId: 'outer' },
  ], { space: 'world' });

  const outerMesh = outer.children[0] as THREE.Mesh;

  assert.equal(inner.userData.visualStackIndex, 0);
  assert.equal(outer.userData.visualStackIndex, 1);
  assert.equal(outerMesh.renderOrder, 1);
  assert.equal(isCoplanarOffsetMaterial(outerMesh.material as THREE.Material), true);
});

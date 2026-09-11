import test from 'node:test';
import assert from 'node:assert/strict';
import type { RefObject } from 'react';
import * as THREE from 'three';

import { URDFLink, URDFVisual } from '@/core/parsers/urdf/loader/URDFClasses';

import { markVisualObject, rebuildLinkMeshMapFromRobot } from './robotLoaderPatchUtils';

test('rebuildLinkMeshMapFromRobot restores collision meshes from collider ancestors when collisions become visible', () => {
  const robot = new THREE.Group();
  const link = new URDFLink();
  link.name = 'base_link';

  const visualGroup = new URDFVisual();
  const visualMesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0x999999 }),
  );
  visualMesh.userData.parentLinkName = 'base_link';
  visualGroup.add(visualMesh);

  const collisionGroup = new THREE.Group();
  collisionGroup.userData.isCollisionGroup = true;
  collisionGroup.userData.parentLinkName = 'base_link';
  collisionGroup.visible = false;

  const collisionMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.1),
    new THREE.MeshBasicMaterial({ color: 0xff0000 }),
  );
  collisionGroup.add(collisionMesh);

  link.add(visualGroup);
  link.add(collisionGroup);
  robot.add(link);

  const linkMeshMapRef = {
    current: new Map<string, THREE.Mesh[]>(),
  } as RefObject<Map<string, THREE.Mesh[]>>;

  rebuildLinkMeshMapFromRobot(linkMeshMapRef, robot);

  assert.deepEqual(linkMeshMapRef.current.get('base_link:visual'), [visualMesh]);
  assert.equal(linkMeshMapRef.current.has('base_link:collision'), false);

  collisionGroup.visible = true;
  rebuildLinkMeshMapFromRobot(linkMeshMapRef, robot);

  assert.deepEqual(linkMeshMapRef.current.get('base_link:visual'), [visualMesh]);
  assert.deepEqual(linkMeshMapRef.current.get('base_link:collision'), [collisionMesh]);
  assert.equal(collisionMesh.userData.parentLinkName, 'base_link');
  assert.equal(collisionMesh.userData.isCollisionMesh, true);
  assert.equal(collisionMesh.userData.isVisualMesh, false);
});

test('markVisualObject does not tint baked OBJ vertex colors with link fallback color', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );
  geometry.setAttribute(
    'color',
    new THREE.Float32BufferAttribute([0.67, 0.69, 0.77, 0.67, 0.69, 0.77, 0.67, 0.69, 0.77], 3),
  );
  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    vertexColors: true,
  });
  material.userData.usesVertexColors = true;
  const mesh = new THREE.Mesh(geometry, material);

  markVisualObject(mesh, 'FL_calf', '#000000', true);

  assert.equal(mesh.userData.parentLinkName, 'FL_calf');
  assert.equal(mesh.visible, true);
  assert.equal((mesh.material as THREE.MeshStandardMaterial).vertexColors, true);
  assert.equal((mesh.material as THREE.MeshStandardMaterial).color.getHexString(), 'ffffff');
});

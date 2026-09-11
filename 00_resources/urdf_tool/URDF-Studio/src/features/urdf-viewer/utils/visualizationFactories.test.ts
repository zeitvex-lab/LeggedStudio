import assert from 'node:assert/strict';
import test from 'node:test';

import * as THREE from 'three';
import type { LineSegments, Material, Mesh } from 'three';

import { ignoreRaycast } from '@/shared/utils/three/ignoreRaycast';
import {
  createInertiaBox,
  createLinkIkHandle,
  createOriginAxes,
} from './visualizationFactories.ts';

function collectMeshMaterials(originAxes: ReturnType<typeof createOriginAxes>) {
  const materials: Material[] = [];

  originAxes.traverse((child) => {
    if (!(child as Mesh).isMesh) {
      return;
    }

    const material = (child as Mesh).material;
    if (Array.isArray(material)) {
      materials.push(...material);
      return;
    }

    materials.push(material);
  });

  return materials;
}

test('createOriginAxes defaults to participating in depth occlusion', () => {
  const originAxes = createOriginAxes(0.1);
  const materials = collectMeshMaterials(originAxes);

  assert.ok(materials.length > 0, 'origin axes should create mesh materials');
  materials.forEach((material) => {
    assert.equal(material.depthTest, true);
    assert.equal(material.depthWrite, true);
    assert.equal(material.transparent, false);
  });
});

test('createOriginAxes renders rod-style axes without arrow heads', () => {
  const originAxes = createOriginAxes(0.1);
  const meshes: Mesh[] = [];
  originAxes.traverse((child) => {
    if ((child as Mesh).isMesh) meshes.push(child as Mesh);
  });

  assert.equal(meshes.length, 3, 'origin axes should render exactly three rods (X/Y/Z)');
  meshes.forEach((mesh) => {
    assert.equal(
      (mesh.geometry as THREE.BufferGeometry).type,
      'CylinderGeometry',
      'each axis should be a plain rod (no ConeGeometry arrow head)',
    );
  });
});

test('createInertiaBox uses the fill surface for hover and keeps the outline decorative', () => {
  const inertiaBox = createInertiaBox(1, 2, 3, new THREE.Quaternion());
  const fillMesh = inertiaBox.children.find((child) => (child as Mesh).isMesh) as Mesh | undefined;
  const outline = inertiaBox.children.find((child) => (child as LineSegments).isLineSegments) as
    | LineSegments
    | undefined;

  assert.ok(fillMesh, 'inertia box should include a filled mesh');
  assert.ok(outline, 'inertia box should include an outline');
  assert.equal((fillMesh.material as Material).depthTest, true);
  assert.equal((fillMesh.material as Material).depthWrite, false);
  assert.equal((outline.material as Material).depthTest, true);
  assert.equal((outline.material as Material).depthWrite, false);
  assert.notEqual(fillMesh?.raycast, ignoreRaycast);
  assert.equal(outline?.raycast, ignoreRaycast);
});

test('createLinkIkHandle keeps IK helpers hidden while preserving a pick target', () => {
  const ikHandle = createLinkIkHandle(0.03);
  const pickTarget = ikHandle.children.find((child) => (child as Mesh).isMesh) as Mesh | undefined;
  const outline = ikHandle.children.find((child) => (child as LineSegments).isLineSegments);

  assert.ok(pickTarget, 'ik handle should keep an invisible pick target');
  assert.equal(outline, undefined);
  assert.equal(pickTarget?.name, '__ik_handle_pick_target__');
  assert.equal(pickTarget?.userData.viewerHelperKind, 'ik-handle');
  assert.equal((pickTarget?.material as Material).opacity, 0);
  assert.equal((pickTarget?.material as Material & { colorWrite?: boolean }).colorWrite, false);
});

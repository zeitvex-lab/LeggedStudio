import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { GENERATED_OBJ_MATERIAL_USER_DATA_KEY } from '@/core/loaders/objModelData';
import {
  disposeObjPreviewClone,
  replaceObjPreviewMeshMaterials,
  shouldOverrideObjPreviewMesh,
} from './OBJRendererImpl.tsx';

function trackDisposeCalls<T extends THREE.Material | THREE.BufferGeometry>(resource: T) {
  let disposeCalls = 0;
  const originalDispose = resource.dispose.bind(resource);
  resource.dispose = (() => {
    disposeCalls += 1;
    return originalDispose();
  }) as T['dispose'];
  return () => disposeCalls;
}

test('replaceObjPreviewMeshMaterials disposes generated OBJ materials when swapping to a shared override', () => {
  const generatedMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000 });
  generatedMaterial.userData = {
    ...(generatedMaterial.userData ?? {}),
    [GENERATED_OBJ_MATERIAL_USER_DATA_KEY]: true,
  };
  const sharedMaterial = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), generatedMaterial);
  const getDisposeCalls = trackDisposeCalls(generatedMaterial);

  try {
    replaceObjPreviewMeshMaterials([mesh], sharedMaterial);

    assert.equal(mesh.material, sharedMaterial);
    assert.equal(getDisposeCalls(), 1);
  } finally {
    mesh.geometry.dispose();
    sharedMaterial.dispose();
  }
});

test('disposeObjPreviewClone releases clone-owned OBJ resources without disposing the shared override material', () => {
  const sharedMaterial = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const mesh = new THREE.Mesh(geometry, sharedMaterial);
  const clone = new THREE.Group();
  clone.add(mesh);

  const getGeometryDisposeCalls = trackDisposeCalls(geometry);
  const getSharedMaterialDisposeCalls = trackDisposeCalls(sharedMaterial);

  disposeObjPreviewClone(clone, sharedMaterial);

  assert.equal(getGeometryDisposeCalls(), 1);
  assert.equal(getSharedMaterialDisposeCalls(), 0);

  sharedMaterial.dispose();
});

test('shouldOverrideObjPreviewMesh only overrides generated OBJ materials', () => {
  const generatedMesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({ color: 0xffffff }),
  );
  (generatedMesh.material as THREE.Material).userData = {
    ...((generatedMesh.material as THREE.Material).userData ?? {}),
    [GENERATED_OBJ_MATERIAL_USER_DATA_KEY]: true,
  };
  const texturedMesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshStandardMaterial({
      color: 0xffffff,
      map: new THREE.Texture(),
    }),
  );
  const vertexColorGeometry = new THREE.BoxGeometry(1, 1, 1);
  vertexColorGeometry.setAttribute(
    'color',
    new THREE.Float32BufferAttribute(
      new Array(vertexColorGeometry.attributes.position.count * 3).fill(1),
      3,
    ),
  );
  const vertexColorMesh = new THREE.Mesh(
    vertexColorGeometry,
    new THREE.MeshStandardMaterial({ color: 0xffffff }),
  );

  try {
    assert.equal(shouldOverrideObjPreviewMesh(generatedMesh), true);
    assert.equal(shouldOverrideObjPreviewMesh(texturedMesh), false);
    assert.equal(shouldOverrideObjPreviewMesh(vertexColorMesh), false);
    assert.equal(shouldOverrideObjPreviewMesh(texturedMesh, true), false);
  } finally {
    generatedMesh.geometry.dispose();
    (generatedMesh.material as THREE.Material).dispose();
    texturedMesh.geometry.dispose();
    (texturedMesh.material as THREE.Material).dispose();
    vertexColorGeometry.dispose();
    (vertexColorMesh.material as THREE.Material).dispose();
  }
});

test('replaceObjPreviewMeshMaterials does not dispose shared override materials during material refreshes', () => {
  const generatedMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000 });
  generatedMaterial.userData = {
    ...(generatedMaterial.userData ?? {}),
    [GENERATED_OBJ_MATERIAL_USER_DATA_KEY]: true,
  };
  const firstSharedMaterial = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
  const secondSharedMaterial = new THREE.MeshBasicMaterial({ color: 0x0000ff });
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), generatedMaterial);
  const getFirstSharedDisposeCalls = trackDisposeCalls(firstSharedMaterial);

  try {
    replaceObjPreviewMeshMaterials([mesh], firstSharedMaterial);
    replaceObjPreviewMeshMaterials([mesh], secondSharedMaterial);

    assert.equal(mesh.material, secondSharedMaterial);
    assert.equal(getFirstSharedDisposeCalls(), 0);
  } finally {
    mesh.geometry.dispose();
    firstSharedMaterial.dispose();
    secondSharedMaterial.dispose();
  }
});

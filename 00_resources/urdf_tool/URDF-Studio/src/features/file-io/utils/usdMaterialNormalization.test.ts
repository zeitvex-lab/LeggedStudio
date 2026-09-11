import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  createUsdBaseMaterial,
  normalizeUsdRenderableMaterials,
} from './usdMaterialNormalization.ts';

test('normalizeUsdRenderableMaterials converts renderable materials to MeshStandardMaterial instances', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshBasicMaterial({
      color: '#123456',
      opacity: 0.35,
      transparent: true,
      side: THREE.DoubleSide,
      name: 'basic-source',
    }),
  );

  normalizeUsdRenderableMaterials(mesh, '#abcdef');

  assert.ok(mesh.material instanceof THREE.MeshStandardMaterial);
  assert.equal(mesh.material.name, 'basic-source');
  assert.equal(mesh.material.transparent, true);
  assert.equal(mesh.material.opacity, 0.35);
  assert.equal(mesh.material.side, THREE.FrontSide);
  assert.equal(mesh.material.color.getHexString(), '123456');
});

test('normalizeUsdRenderableMaterials keeps multi-material meshes intact instead of splitting them into variant meshes', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], 3),
  );
  geometry.clearGroups();
  geometry.addGroup(0, 3, 0);
  geometry.addGroup(3, 3, 1);

  const mesh = new THREE.Mesh(geometry, [
    new THREE.MeshBasicMaterial({ color: '#ff0000', name: 'shell' }),
    new THREE.MeshBasicMaterial({ color: '#00ff00', name: 'logo' }),
  ]);
  mesh.name = 'panel';

  const root = new THREE.Group();
  root.add(mesh);

  normalizeUsdRenderableMaterials(root, '#abcdef');

  assert.equal(root.children.length, 1);
  assert.equal(root.children[0], mesh);
  assert.ok(Array.isArray(mesh.material));
  assert.equal(mesh.material.length, 2);

  const [shellMaterial, logoMaterial] = mesh.material;
  assert.ok(shellMaterial instanceof THREE.MeshStandardMaterial);
  assert.ok(logoMaterial instanceof THREE.MeshStandardMaterial);
  assert.equal(shellMaterial.name, 'shell');
  assert.equal(logoMaterial.name, 'logo');
  assert.equal(shellMaterial.color.getHexString(), 'ff0000');
  assert.equal(logoMaterial.color.getHexString(), '00ff00');
  assert.deepEqual(
    geometry.groups.map((group) => group.materialIndex),
    [0, 1],
  );
});

test('normalizeUsdRenderableMaterials preserves vertex-colored OBJ materials on a neutral base', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );
  geometry.setAttribute(
    'color',
    new THREE.Float32BufferAttribute([0.67, 0.69, 0.77, 0.67, 0.69, 0.77, 0, 0, 0], 3),
  );

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshPhongMaterial({
      color: '#000000',
      vertexColors: true,
      name: 'material_black_patch',
    }),
  );

  normalizeUsdRenderableMaterials(mesh, '#000000');

  assert.ok(mesh.material instanceof THREE.MeshStandardMaterial);
  assert.equal(mesh.material.name, 'material_black_patch');
  assert.equal(mesh.material.vertexColors, true);
  assert.equal(mesh.material.toneMapped, false);
  assert.equal(mesh.material.color.getHexString(), 'ffffff');
  assert.equal(mesh.material.userData.usesVertexColors, true);
});

test('normalizeUsdRenderableMaterials fixes already-standard vertex-colored materials', () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
  );
  geometry.setAttribute(
    'color',
    new THREE.Float32BufferAttribute([0.67, 0.69, 0.77, 0.67, 0.69, 0.77, 0, 0, 0], 3),
  );

  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      color: '#000000',
      vertexColors: true,
    }),
  );

  normalizeUsdRenderableMaterials(mesh, '#000000');

  assert.ok(mesh.material instanceof THREE.MeshStandardMaterial);
  assert.equal(mesh.material.vertexColors, true);
  assert.equal(mesh.material.color.getHexString(), 'ffffff');
});

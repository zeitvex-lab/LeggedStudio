import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import * as THREE from 'three';

import { DAERenderer, GLTFRenderer, OBJRenderer, STLRenderer } from './MeshRenderers';
import { MeshAssetNode } from './MeshAssetNode';

test('MeshAssetNode routes STL assets to STLRenderer', () => {
  const material = new THREE.MeshBasicMaterial();

  try {
    const element = MeshAssetNode({
      meshPath: 'meshes/base.stl',
      assets: { 'meshes/base.stl': 'blob:stl' },
      material,
    }) as React.ReactElement<React.ComponentProps<typeof STLRenderer>>;

    assert.equal(element.type, STLRenderer);
    assert.equal(element.props.url, 'blob:stl');
    assert.equal(element.props.enableShadows, true);
  } finally {
    material.dispose();
  }
});

test('MeshAssetNode routes OBJ assets with the derived base directory', () => {
  const material = new THREE.MeshBasicMaterial();

  try {
    const element = MeshAssetNode({
      meshPath: 'robots/go2/meshes/thigh.obj',
      assets: { 'robots/go2/meshes/thigh.obj': 'blob:obj' },
      material,
      color: '#abcdef',
      preserveOriginalMaterial: true,
    }) as React.ReactElement<React.ComponentProps<typeof OBJRenderer>>;

    assert.equal(element.type, OBJRenderer);
    assert.equal(element.props.url, 'blob:obj');
    assert.equal(element.props.color, '#abcdef');
    assert.equal(element.props.assetBaseDir, 'robots/go2/meshes/');
    assert.equal(element.props.logicalAssetPath, 'robots/go2/meshes/thigh.obj');
    assert.equal(element.props.preserveOriginalMaterial, true);
    assert.equal(element.props.enableShadows, true);
  } finally {
    material.dispose();
  }
});

test('MeshAssetNode routes Collada and GLTF assets with material preservation flags', () => {
  const daeMaterial = new THREE.MeshBasicMaterial();
  const gltfMaterial = new THREE.MeshBasicMaterial();

  try {
    const daeElement = MeshAssetNode({
      meshPath: 'meshes/visual.dae',
      assets: { 'meshes/visual.dae': 'blob:dae' },
      material: daeMaterial,
      normalizeRoot: true,
      preserveOriginalMaterial: true,
    }) as React.ReactElement<React.ComponentProps<typeof DAERenderer>>;
    assert.equal(daeElement.type, DAERenderer);
    assert.equal(daeElement.props.normalizeRoot, true);
    assert.equal(daeElement.props.preserveOriginalMaterial, true);
    assert.equal(daeElement.props.enableShadows, true);

    const gltfElement = MeshAssetNode({
      meshPath: 'meshes/visual.glb',
      assets: { 'meshes/visual.glb': 'blob:gltf' },
      material: gltfMaterial,
      enableShadows: false,
      preserveOriginalMaterial: true,
    }) as React.ReactElement<React.ComponentProps<typeof GLTFRenderer>>;
    assert.equal(gltfElement.type, GLTFRenderer);
    assert.equal(gltfElement.props.preserveOriginalMaterial, true);
    assert.equal(gltfElement.props.enableShadows, false);
  } finally {
    daeMaterial.dispose();
    gltfMaterial.dispose();
  }
});

test('MeshAssetNode returns caller-provided fallback nodes for missing and unknown assets', () => {
  const material = new THREE.MeshBasicMaterial();
  const missingNode = React.createElement('missing-state');
  const unknownNode = React.createElement('unknown-state');

  try {
    const missingElement = MeshAssetNode({
      meshPath: 'meshes/missing.obj',
      assets: {},
      material,
      missingContent: missingNode,
    }) as React.ReactElement;
    assert.equal(missingElement.type, 'missing-state');

    const unknownElement = MeshAssetNode({
      meshPath: 'meshes/model.xyz',
      assets: { 'meshes/model.xyz': 'blob:xyz' },
      material,
      unknownContent: unknownNode,
    }) as React.ReactElement;
    assert.equal(unknownElement.type, 'unknown-state');
  } finally {
    material.dispose();
  }
});

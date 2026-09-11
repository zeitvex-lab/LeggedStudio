import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as THREE from 'three';

import { createLoadingManager } from './index';
import {
  createSceneFromSerializedColladaData,
  parseColladaSceneData,
} from './colladaWorkerSceneData.ts';

type WorkerImageGlobalSnapshot = {
  DOMParser: typeof globalThis.DOMParser;
  Image: typeof globalThis.Image;
  HTMLImageElement: typeof globalThis.HTMLImageElement;
  XMLSerializer: typeof globalThis.XMLSerializer;
  document: typeof globalThis.document;
};

function captureWorkerImageGlobals(): WorkerImageGlobalSnapshot {
  return {
    DOMParser: globalThis.DOMParser,
    Image: globalThis.Image,
    HTMLImageElement: globalThis.HTMLImageElement,
    XMLSerializer: globalThis.XMLSerializer,
    document: globalThis.document,
  };
}

function restoreWorkerImageGlobals(snapshot: WorkerImageGlobalSnapshot): void {
  if (snapshot.DOMParser) {
    globalThis.DOMParser = snapshot.DOMParser;
  } else {
    Reflect.deleteProperty(globalThis, 'DOMParser');
  }

  if (snapshot.document) {
    globalThis.document = snapshot.document;
  } else {
    Reflect.deleteProperty(globalThis, 'document');
  }

  if (snapshot.HTMLImageElement) {
    globalThis.HTMLImageElement = snapshot.HTMLImageElement;
  } else {
    Reflect.deleteProperty(globalThis, 'HTMLImageElement');
  }

  if (snapshot.Image) {
    globalThis.Image = snapshot.Image;
  } else {
    Reflect.deleteProperty(globalThis, 'Image');
  }

  if (snapshot.XMLSerializer) {
    globalThis.XMLSerializer = snapshot.XMLSerializer;
  } else {
    Reflect.deleteProperty(globalThis, 'XMLSerializer');
  }
}

function getFirstMesh(root: THREE.Object3D): THREE.Mesh {
  let foundMesh: THREE.Mesh | null = null as THREE.Mesh | null;

  root.traverse((child) => {
    if (!foundMesh && (child as THREE.Mesh).isMesh) {
      foundMesh = child as THREE.Mesh;
    }
  });

  assert.ok(foundMesh, 'expected Collada scene to contain a mesh');
  return foundMesh;
}

test('textured Collada worker scene data restores image-backed textures without DOM globals', () => {
  const meshPath = 'test/gazebo_models/checkerboard_plane/meshes/checkerboard_plane.dae';
  const colladaText = fs.readFileSync(meshPath, 'utf8');
  const snapshot = captureWorkerImageGlobals();

  Reflect.deleteProperty(globalThis, 'DOMParser');
  Reflect.deleteProperty(globalThis, 'document');
  Reflect.deleteProperty(globalThis, 'HTMLImageElement');
  Reflect.deleteProperty(globalThis, 'Image');
  Reflect.deleteProperty(globalThis, 'XMLSerializer');

  try {
    const serializedScene = parseColladaSceneData(colladaText, meshPath);
    const restoredScene = createSceneFromSerializedColladaData(serializedScene);
    const restoredMesh = getFirstMesh(restoredScene);
    const restoredMaterial = restoredMesh.material as THREE.MeshPhongMaterial;

    assert.ok(restoredMaterial.map, 'expected textured Collada scene to restore material.map');
    assert.equal(typeof globalThis.HTMLImageElement, 'function');
    assert.ok(
      restoredMaterial.map.source.data instanceof globalThis.HTMLImageElement,
      'expected textured Collada scene to restore an image-backed source in worker mode',
    );
    assert.match(String(restoredMaterial.map.source.data.src), /checker\.png$/);
  } finally {
    restoreWorkerImageGlobals(snapshot);
  }
});

test('createSceneFromSerializedColladaData resolves blob-relative Collada textures through the loading manager', () => {
  const daePath = 'test/unitree_ros/robots/aliengo_description/meshes/trunk.dae';
  const pngPath = 'test/unitree_ros/robots/aliengo_description/meshes/trunk_uv_base_final.png';
  const colladaText = fs.readFileSync(daePath, 'utf8');
  const textureDataUrl = `data:image/png;base64,${fs.readFileSync(pngPath).toString('base64')}`;
  const serializedScene = parseColladaSceneData(
    colladaText,
    'blob:http://127.0.0.1:4204/fake-trunk-dae',
  );
  const manager = createLoadingManager(
    {
      'aliengo_description/meshes/trunk_uv_base_final.png': textureDataUrl,
    },
    'aliengo_description/urdf/',
  );
  const restoredScene = createSceneFromSerializedColladaData(serializedScene, { manager });
  const restoredMesh = getFirstMesh(restoredScene);
  const restoredMaterial = restoredMesh.material as THREE.MeshPhongMaterial;

  assert.ok(restoredMaterial.map, 'expected Aliengo trunk Collada scene to restore material.map');
  assert.equal(
    (restoredMaterial.map.source.data as { src?: string }).src,
    textureDataUrl,
    'expected blob-relative Collada texture URL to be remapped through the asset manager',
  );
});

test('createSceneFromSerializedColladaData applies Collada unit meter scaling for Aliengo calf truth', () => {
  const daePath = 'test/unitree_ros/robots/aliengo_description/meshes/calf.dae';
  const colladaText = fs.readFileSync(daePath, 'utf8');
  const serializedScene = parseColladaSceneData(colladaText, daePath);
  const restoredScene = createSceneFromSerializedColladaData(serializedScene);
  const bounds = new THREE.Box3().setFromObject(restoredScene);
  const size = new THREE.Vector3();
  bounds.getSize(size);

  assert.equal(serializedScene.unitScale, 0.0254);
  assert.ok(
    size.z < 0.5,
    `expected Aliengo calf mesh to stay near URDF truth scale after applying unit meter, got z=${size.z}`,
  );
});

test('parseColladaSceneData tolerates Gazebo Collada images without init_from nodes', () => {
  const daePath = 'test/gazebo_models/arm_part/meshes/arm.dae';
  const colladaText = fs.readFileSync(daePath, 'utf8');
  const serializedScene = parseColladaSceneData(colladaText, daePath);
  const restoredScene = createSceneFromSerializedColladaData(serializedScene);
  if (serializedScene.kind === 'fast-mesh-v1') {
    throw new Error('expected legacy Collada JSON scene data');
  }
  const sceneJson = serializedScene.sceneJson as {
    images?: Array<{ url?: string | string[] }>;
  };

  assert.ok(getFirstMesh(restoredScene), 'expected Gazebo arm Collada scene to restore a mesh');
  assert.equal(
    (sceneJson.images ?? []).every((image) => {
      if (typeof image.url === 'string') {
        return image.url.length > 0;
      }

      if (Array.isArray(image.url)) {
        return image.url.every((entry) => typeof entry === 'string' && entry.length > 0);
      }

      return false;
    }),
    true,
    'expected serialized Gazebo arm Collada images to either be removed or retain a concrete url',
  );
});

test('parseColladaSceneData strips broken Gazebo image bindings before Three.js falls back noisily', () => {
  const daePath = 'test/gazebo_models/arm_part/meshes/arm.dae';
  const colladaText = fs.readFileSync(daePath, 'utf8');
  const originalConsoleWarn = console.warn;
  const warnings: unknown[][] = [];

  console.warn = (...args) => {
    warnings.push(args);
  };

  try {
    const serializedScene = parseColladaSceneData(colladaText, daePath);
    const restoredScene = createSceneFromSerializedColladaData(serializedScene);

    assert.ok(getFirstMesh(restoredScene), 'expected Gazebo arm Collada scene to restore a mesh');
  } finally {
    console.warn = originalConsoleWarn;
  }

  assert.equal(
    warnings.some((entry) => String(entry?.[0] ?? '').includes(`Couldn't find image with ID`)),
    false,
    'expected Gazebo arm Collada parse to avoid missing-image fallback warnings',
  );
  assert.equal(
    warnings.some((entry) => String(entry?.[0] ?? '').includes(`Couldn't create texture with ID`)),
    false,
    'expected Gazebo arm Collada parse to avoid missing-texture fallback warnings',
  );
});

test('parseColladaSceneData remaps Gazebo image-bound texture references to sampler bindings', () => {
  const daePath = 'test/gazebo_models/coke_can/meshes/coke_can.dae';
  const colladaText = fs.readFileSync(daePath, 'utf8');
  const originalConsoleWarn = console.warn;
  const warnings: unknown[][] = [];

  console.warn = (...args) => {
    warnings.push(args);
  };

  try {
    const serializedScene = parseColladaSceneData(colladaText, daePath);
    const restoredScene = createSceneFromSerializedColladaData(serializedScene);
    const restoredMesh = getFirstMesh(restoredScene);
    const restoredMaterial = restoredMesh.material as THREE.MeshPhongMaterial;

    assert.ok(
      restoredMaterial.map,
      'expected Gazebo coke can Collada scene to restore material.map',
    );
  } finally {
    console.warn = originalConsoleWarn;
  }

  assert.equal(
    warnings.some((entry) =>
      String(entry?.[0] ?? '').includes('THREE.ColladaLoader: Undefined sampler'),
    ),
    false,
    'expected Gazebo coke can Collada parse to avoid the undefined sampler fallback warning',
  );
});

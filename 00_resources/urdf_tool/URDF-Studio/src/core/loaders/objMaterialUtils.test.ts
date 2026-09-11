import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { MTLLoader } from 'three/examples/jsm/loaders/MTLLoader.js';

import { createLoadingManager } from './meshLoader.ts';
import {
  cloneObjSceneWithOwnedResources,
  createTextAssetContentLookup,
  deriveObjAuthoredMaterialsFromLookup,
  loadObjScene,
  parseObjMaterialLibraries,
  rewriteMtlTextureReferencesForManager,
} from './objMaterialUtils.ts';

test('rewriteMtlTextureReferencesForManager resolves relative and model texture references to manager-resolvable paths', () => {
  const materialText = [
    'newmtl Ambulance',
    '\tmap_Kd ambulance.png',
    '\tmap_Ka model://suv/materials/textures/wheels_01.png',
  ].join('\n');

  const rewritten = rewriteMtlTextureReferencesForManager(
    materialText,
    'test/gazebo_models/ambulance/meshes/ambulance.mtl',
  );

  assert.match(rewritten, /map_Kd test\/gazebo_models\/ambulance\/meshes\/ambulance\.png$/m);
  assert.match(rewritten, /map_Ka suv\/materials\/textures\/wheels_01\.png$/m);
  // The resolved path (with extension) is kept verbatim, not pre-flattened to a blob: URL.
  assert.doesNotMatch(rewritten, /resolved:|blob:/);
});

test('rewriteMtlTextureReferencesForManager preserves texture directive options when rewriting the final path token', () => {
  const rewritten = rewriteMtlTextureReferencesForManager(
    'map_Kd -s 1 1 1 -o 0 0 0 ambulance.png',
    'test/gazebo_models/ambulance/meshes/ambulance.mtl',
  );

  assert.match(
    rewritten,
    /^map_Kd -s 1 1 1 -o 0 0 0 test\/gazebo_models\/ambulance\/meshes\/ambulance\.png$/,
  );
});

test('rewriteMtlTextureReferencesForManager keeps the file extension so getHandler can pick TGA/HDR decoders', () => {
  const rewritten = rewriteMtlTextureReferencesForManager(
    ['newmtl M', 'map_Kd wood.tga', 'bump normal.hdr'].join('\n'),
    'models/robot/part.mtl',
  );

  // Extension must survive (not be flattened into an extensionless blob: URL) so that
  // manager.getHandler() routes these through the TGA/HDR decoders at load time.
  assert.match(rewritten, /models\/robot\/wood\.tga$/m);
  assert.match(rewritten, /models\/robot\/normal\.hdr$/m);
});

test('parseObjMaterialLibraries splits multi-library directives in declaration order', () => {
  const materialLibraries = parseObjMaterialLibraries(
    ['mtllib first.mtl second.mtl', 'mtllib third.mtl'].join('\n'),
  );

  assert.deepEqual(materialLibraries, ['first.mtl', 'second.mtl', 'third.mtl']);
});

test('deriveObjAuthoredMaterialsFromLookup keeps authored materials from every referenced MTL', () => {
  const lookup = createTextAssetContentLookup({
    'robot/model.obj': 'mtllib first.mtl second.mtl',
    'robot/first.mtl': ['newmtl First', 'Kd 1 0 0'].join('\n'),
    'robot/second.mtl': ['newmtl Second', 'map_Kd textures/second.png'].join('\n'),
    'robot/textures/second.png': 'placeholder-texture-bytes',
  });

  const authoredMaterials = deriveObjAuthoredMaterialsFromLookup('robot/model.obj', lookup);

  assert.equal(authoredMaterials.length, 2);
  assert.deepEqual(
    authoredMaterials.map((material) => material.name),
    ['First', 'Second'],
  );
  assert.equal(authoredMaterials[0]?.color, '#ff0000');
  assert.equal(authoredMaterials[1]?.texture, 'robot/textures/second.png');
});

test('loadObjScene merges every reachable material library before parsing MTL content', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const originalParse = MTLLoader.prototype.parse;
  const materialTextsSeen: string[] = [];
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      [
        'mtllib first.mtl second.mtl',
        'o Mesh',
        'v 0 0 0',
        'v 1 0 0',
        'v 0 1 0',
        'usemtl First',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/first.mtl', 'newmtl First\nKd 1 0 0'],
    ['resolved:robot/second.mtl', 'newmtl Second\nKd 0 1 0'],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    if (!body) {
      return new Response('', { status: 404, statusText: 'Not Found' });
    }

    return new Response(body, { status: 200, statusText: 'OK' });
  };

  MTLLoader.prototype.parse = function patchedParse(text, path) {
    materialTextsSeen.push(text);
    return originalParse.call(this, text, path);
  };

  try {
    await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
  } finally {
    globalThis.fetch = originalFetch;
    MTLLoader.prototype.parse = originalParse;
  }

  assert.equal(materialTextsSeen.length, 1);
  assert.match(materialTextsSeen[0] ?? '', /newmtl First/);
  assert.match(materialTextsSeen[0] ?? '', /newmtl Second/);
});

test('loadObjScene tolerates missing mtllib files and still parses bare OBJ geometry', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      ['mtllib material.mtl', 'o Mesh', 'v 0 0 0', 'v 1 0 0', 'v 0 1 0', 'f 1 2 3'].join('\n'),
    ],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    if (!body) {
      return new Response('', { status: 404, statusText: 'Not Found' });
    }

    return new Response(body, { status: 200, statusText: 'OK' });
  };

  try {
    const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
    assert.ok(scene.children.length > 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene tolerates missing mtllib files under strict asset managers', async () => {
  const manager = createLoadingManager(
    {
      'robot/model.obj': `data:text/plain;charset=utf-8,${encodeURIComponent(
        ['mtllib material.mtl', 'o Mesh', 'v 0 0 0', 'v 1 0 0', 'v 0 1 0', 'f 1 2 3'].join('\n'),
      )}`,
    },
    'robot/',
  );

  const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
  assert.ok(scene.children.length > 0);
});

test('loadObjScene keeps vertex-colored OBJ meshes on a neutral material base', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/calf.obj',
      [
        'mtllib calf.mtl',
        'o Calf',
        'v 0 0 0 0.67 0.69 0.77',
        'v 1 0 0 0.67 0.69 0.77',
        'v 0 1 0 0.67 0.69 0.77',
        'usemtl BlackPatch',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/calf.mtl', 'newmtl BlackPatch\nKd 0 0 0'],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    if (!body) {
      return new Response('', { status: 404, statusText: 'Not Found' });
    }

    return new Response(body, { status: 200, statusText: 'OK' });
  };

  try {
    const scene = await loadObjScene('robot/calf.obj', manager, 'robot/calf.obj');
    const mesh = scene.children.find((child): child is THREE.Mesh => (child as THREE.Mesh).isMesh);
    assert.ok(mesh, 'expected OBJ loader to create a mesh');
    assert.ok(mesh.geometry.getAttribute('color'));
    const material = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(material.vertexColors, true);
    assert.equal(material.color.getHexString(), 'ffffff');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene applies MTL materials when usemtl casing differs from newmtl', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      [
        'mtllib model.mtl',
        'o Mesh',
        'v 0 0 0',
        'v 1 0 0',
        'v 0 1 0',
        'usemtl painted',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/model.mtl', 'newmtl Painted\nKd 1 0 0'],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    return body
      ? new Response(body, { status: 200, statusText: 'OK' })
      : new Response('', { status: 404, statusText: 'Not Found' });
  };

  try {
    const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
    const mesh = scene.children.find((child): child is THREE.Mesh => (child as THREE.Mesh).isMesh);
    assert.ok(mesh, 'expected OBJ loader to create a mesh');
    const material = mesh.material as THREE.MeshPhongMaterial;
    assert.equal(material.color.getHexString(), 'ff0000');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene falls back to the only MTL material when usemtl does not match', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      [
        'mtllib model.mtl',
        'o Mesh',
        'v 0 0 0',
        'v 1 0 0',
        'v 0 1 0',
        'usemtl Mismatch',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/model.mtl', 'newmtl OnlyMaterial\nKd 0 0 1'],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    return body
      ? new Response(body, { status: 200, statusText: 'OK' })
      : new Response('', { status: 404, statusText: 'Not Found' });
  };

  try {
    const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
    const mesh = scene.children.find((child): child is THREE.Mesh => (child as THREE.Mesh).isMesh);
    assert.ok(mesh, 'expected OBJ loader to create a mesh');
    const material = mesh.material as THREE.MeshPhongMaterial;
    assert.equal(material.color.getHexString(), '0000ff');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene does not force a material when several MTL materials all mismatch usemtl', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      [
        'mtllib model.mtl',
        'o Mesh',
        'v 0 0 0',
        'v 1 0 0',
        'v 0 1 0',
        'usemtl Mismatch',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/model.mtl', ['newmtl A', 'Kd 1 0 0', 'newmtl B', 'Kd 0 1 0'].join('\n')],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    return body
      ? new Response(body, { status: 200, statusText: 'OK' })
      : new Response('', { status: 404, statusText: 'Not Found' });
  };

  try {
    const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
    const mesh = scene.children.find((child): child is THREE.Mesh => (child as THREE.Mesh).isMesh);
    assert.ok(mesh, 'expected OBJ loader to create a mesh');
    const material = mesh.material as THREE.MeshPhongMaterial;
    const hex = material.color.getHexString();
    assert.notEqual(hex, 'ff0000');
    assert.notEqual(hex, '00ff00');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene keeps vertex-colored OBJ neutral even when a single MTL material could match', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      [
        'mtllib model.mtl',
        'o Mesh',
        'v 0 0 0 0.67 0.69 0.77',
        'v 1 0 0 0.67 0.69 0.77',
        'v 0 1 0 0.67 0.69 0.77',
        'usemtl Mismatch',
        'f 1 2 3',
      ].join('\n'),
    ],
    ['resolved:robot/model.mtl', 'newmtl OnlyMaterial\nKd 0 0 1'],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    return body
      ? new Response(body, { status: 200, statusText: 'OK' })
      : new Response('', { status: 404, statusText: 'Not Found' });
  };

  try {
    const scene = await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
    const mesh = scene.children.find((child): child is THREE.Mesh => (child as THREE.Mesh).isMesh);
    assert.ok(mesh, 'expected OBJ loader to create a mesh');
    assert.ok(mesh.geometry.getAttribute('color'));
    const material = mesh.material as THREE.MeshStandardMaterial;
    assert.equal(material.vertexColors, true);
    assert.equal(material.color.getHexString(), 'ffffff');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('loadObjScene warns once when every declared MTL library fails to load', async () => {
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((url) => `resolved:${url}`);

  const originalFetch = globalThis.fetch;
  const assetTexts = new Map<string, string>([
    [
      'resolved:robot/model.obj',
      ['mtllib missing.mtl', 'o Mesh', 'v 0 0 0', 'v 1 0 0', 'v 0 1 0', 'f 1 2 3'].join('\n'),
    ],
  ]);

  globalThis.fetch = async (input) => {
    const body = assetTexts.get(String(input));
    return body
      ? new Response(body, { status: 200, statusText: 'OK' })
      : new Response('', { status: 404, statusText: 'Not Found' });
  };

  const originalWarn = console.warn;
  const warnings: string[] = [];
  console.warn = (...args: unknown[]) => {
    warnings.push(args.map((arg) => String(arg)).join(' '));
  };

  try {
    await loadObjScene('robot/model.obj', manager, 'robot/model.obj');
  } finally {
    console.warn = originalWarn;
    globalThis.fetch = originalFetch;
  }

  assert.ok(
    warnings.some((message) => message.includes('none could be loaded')),
    'expected an aggregate diagnostic when no MTL library could be loaded',
  );
});

test('cloneObjSceneWithOwnedResources avoids copying OBJ attribute buffers', () => {
  const geometry = new THREE.BufferGeometry();
  const position = new THREE.Float32BufferAttribute(
    [
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
    ],
    3,
  );
  geometry.name = 'triangle-geometry';
  geometry.setAttribute('position', position);
  geometry.addGroup(0, 3, 0);
  geometry.computeBoundingBox();

  const texture = new THREE.Texture();
  const material = new THREE.MeshPhongMaterial({ map: texture });
  const root = new THREE.Group();
  const mesh = new THREE.Mesh(geometry, material);
  root.add(mesh);

  const clonedRoot = cloneObjSceneWithOwnedResources(root);
  const clonedMesh = clonedRoot.children[0] as THREE.Mesh;
  const clonedMaterial = clonedMesh.material as THREE.MeshPhongMaterial;

  assert.notEqual(clonedMesh, mesh);
  assert.notEqual(clonedMesh.geometry, geometry);
  assert.equal(clonedMesh.geometry.getAttribute('position'), position);
  assert.deepEqual(clonedMesh.geometry.groups, [{ start: 0, count: 3, materialIndex: 0 }]);
  assert.notEqual(clonedMaterial, material);
  assert.notEqual(clonedMaterial.map, texture);
});

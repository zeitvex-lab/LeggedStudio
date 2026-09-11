import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import {
  createSceneFromSerializedColladaData,
  parseColladaSceneData,
  type SerializedColladaAttributeData,
} from './colladaWorkerSceneData.ts';
import {
  parseColladaMeshDataWithWasm,
  resetColladaWasmParserForTests,
  setColladaWasmParserModuleUrlForTests,
} from './colladaWasmParser.ts';
import type { MeshLoadPerformanceEntry } from './meshLoadPerformance.ts';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;

function setupCompiledColladaParser(): void {
  const modulePath = path.resolve('public/wasm/collada-mesh-parser/colladaMeshParser.js');
  setColladaWasmParserModuleUrlForTests(pathToFileURL(modulePath).href);
}

function getAttributeArray(attribute: SerializedColladaAttributeData): Float32Array {
  const byteOffset = attribute.byteOffset ?? 0;
  const byteLength = attribute.byteLength ?? attribute.array.byteLength - byteOffset;
  return new Float32Array(
    attribute.array,
    byteOffset,
    byteLength / Float32Array.BYTES_PER_ELEMENT,
  );
}

function summarizeScene(root: THREE.Object3D): {
  groups: THREE.BufferGeometry['groups'];
  materials: string[];
  meshCount: number;
  vertices: number;
} {
  let meshCount = 0;
  let vertices = 0;
  const groups: THREE.BufferGeometry['groups'] = [];
  const materials: string[] = [];

  root.traverse((child) => {
    if (!(child as THREE.Mesh).isMesh) {
      return;
    }

    const mesh = child as THREE.Mesh;
    meshCount += 1;
    vertices += mesh.geometry.getAttribute('position')?.count ?? 0;
    groups.push(...mesh.geometry.groups);
    const meshMaterials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    materials.push(
      ...meshMaterials.map((material) => {
        const color = (material as THREE.Material & { color?: THREE.Color }).color;
        return `${material.name}:${color?.getHexString?.() ?? 'none'}`;
      }),
    );
  });

  return {
    groups,
    materials,
    meshCount,
    vertices,
  };
}

function collectMeshes(root: THREE.Object3D): THREE.Mesh[] {
  const meshes: THREE.Mesh[] = [];
  root.updateMatrixWorld(true);
  root.traverse((child) => {
    if ((child as THREE.Mesh).isMesh) {
      meshes.push(child as THREE.Mesh);
    }
  });
  return meshes;
}

function maxArrayDelta(left: ArrayLike<number>, right: ArrayLike<number>): number {
  assert.equal(right.length, left.length);
  let maxDelta = 0;
  for (let index = 0; index < left.length; index += 1) {
    maxDelta = Math.max(maxDelta, Math.abs(Number(left[index]) - Number(right[index])));
  }
  return maxDelta;
}

test('compiled Collada mesh WASM parser matches Three ColladaLoader geometry and materials for Unitree DAE', async () => {
  setupCompiledColladaParser();

  try {
    const filePath = 'test/unitree_ros/robots/b1_description/meshes/calf.dae';
    const bytes = await fs.readFile(filePath);
    const text = bytes.toString('utf8');
    const fastData = await parseColladaMeshDataWithWasm(bytes, '');
    const fastScene = createSceneFromSerializedColladaData(fastData);
    const slowScene = createSceneFromSerializedColladaData(parseColladaSceneData(text, filePath));

    const fastSummary = summarizeScene(fastScene);
    const slowSummary = summarizeScene(slowScene);

    assert.equal(fastSummary.meshCount, slowSummary.meshCount);
    assert.equal(fastSummary.vertices, slowSummary.vertices);
    assert.deepEqual(fastSummary.groups, slowSummary.groups);
    assert.deepEqual(fastSummary.materials, slowSummary.materials);
    assert.equal(fastData.children.length, 1);
    assert.equal(getAttributeArray(fastData.children[0]!.geometry.position).length, fastSummary.vertices * 3);
    assert.equal(
      new Set(
        [
          fastData.children[0]!.geometry.position,
          fastData.children[0]!.geometry.normal,
          fastData.children[0]!.geometry.uv,
        ]
          .filter(Boolean)
          .map((attribute) => attribute!.array),
      ).size,
      1,
    );
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser rejects unsupported controller scenes', async () => {
  setupCompiledColladaParser();

  try {
    await assert.rejects(
      parseColladaMeshDataWithWasm(
        new TextEncoder().encode('<COLLADA><library_controllers><controller /></library_controllers></COLLADA>'),
        '',
      ),
      /controller|unsupported/i,
    );
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser records internal timing breakdowns', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1">',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const loadPerformance: MeshLoadPerformanceEntry = {
      assetUrl: 'timed.dae',
      format: 'collada',
    };

    await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), '', loadPerformance);

    assert.ok((loadPerformance.colladaWasmFeatureCheckMs ?? -1) >= 0);
    assert.ok((loadPerformance.colladaWasmGeometriesMs ?? -1) >= 0);
    assert.ok((loadPerformance.colladaWasmVisualSceneMs ?? -1) >= 0);
    assert.ok((loadPerformance.colladaWasmWriteResultMs ?? -1) >= 0);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser preserves textured material bindings', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1">',
      '<library_images><image id="image0"><init_from>checker.png</init_from></image></library_images>',
      '<library_effects><effect id="mat-effect"><profile_COMMON>',
      '<newparam sid="surface0"><surface type="2D"><init_from>image0</init_from></surface></newparam>',
      '<newparam sid="sampler0"><sampler2D><source>surface0</source></sampler2D></newparam>',
      '<technique sid="common"><phong>',
      '<diffuse><texture texture="sampler0" texcoord="UVMap"/></diffuse>',
      '<transparent opaque="A_ONE"><color>1 1 1 0.5</color></transparent>',
      '<transparency><float>0.8</float></transparency>',
      '<specular><color>0.2 0.3 0.4 1</color></specular>',
      '<shininess><float>12</float></shininess>',
      '</phong><extra><technique profile="GOOGLEEARTH"><double_sided>1</double_sided></technique></extra></technique>',
      '</profile_COMMON></effect></library_effects>',
      '<library_materials><material id="mat" name="textured"><instance_effect url="#mat-effect"/></material></library_materials>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<source id="uv"><float_array id="uv-array" count="6">0 0 1 0 0 1</float_array>',
      '<technique_common><accessor source="#uv-array" count="3" stride="2"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1" material="mat-symbol">',
      '<input semantic="VERTEX" source="#verts" offset="0"/>',
      '<input semantic="TEXCOORD" source="#uv" offset="1" set="0"/>',
      '<p>0 0 1 1 2 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom">',
      '<bind_material><technique_common><instance_material symbol="mat-symbol" target="#mat"/></technique_common></bind_material>',
      '</instance_geometry></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const fastData = await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), '');
    const material = fastData.children[0]!.materials[0]!;
    assert.equal(material.name, 'textured');
    assert.equal(material.map, 'checker.png');
    assert.equal(material.model, 'phong');
    assert.equal(material.doubleSided, true);
    assert.ok(Math.abs(material.opacity - 0.4) < 1e-6);
    assert.equal(material.transparent, true);

    const manager = new THREE.LoadingManager();
    manager.setURLModifier((url) => (url.endsWith('checker.png') ? 'data:image/png;base64,AA==' : url));
    const scene = createSceneFromSerializedColladaData(fastData, { manager });
    const mesh = collectMeshes(scene)[0]!;
    const sceneMaterial = mesh.material as THREE.MeshPhongMaterial;
    assert.ok(sceneMaterial.map, 'expected fast Collada material.map');
    assert.equal(sceneMaterial.map.colorSpace, THREE.SRGBColorSpace);
    assert.equal(sceneMaterial.map.wrapS, THREE.RepeatWrapping);
    assert.equal(sceneMaterial.side, THREE.DoubleSide);
    assert.ok(Math.abs(sceneMaterial.opacity - 0.4) < 1e-6);
    assert.equal(sceneMaterial.transparent, true);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser resolves direct image texture references', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1">',
      '<library_images><image id="tex0"><init_from>direct.png</init_from></image></library_images>',
      '<library_effects><effect id="mat-effect"><profile_COMMON><technique sid="common">',
      '<lambert><diffuse><texture texture="tex0" texcoord="UVMap"/></diffuse></lambert>',
      '</technique></profile_COMMON></effect></library_effects>',
      '<library_materials><material id="mat" name="direct"><instance_effect url="#mat-effect"/></material></library_materials>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1" material="mat-symbol"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom">',
      '<bind_material><technique_common><instance_material symbol="mat-symbol" target="#mat"/></technique_common></bind_material>',
      '</instance_geometry></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const fastData = await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), '');
    assert.equal(fastData.children[0]!.materials[0]!.map, 'direct.png');
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser supports Collada polygons', async () => {
  setupCompiledColladaParser();

  try {
    const result = await parseColladaMeshDataWithWasm(
      new TextEncoder().encode(
        [
          '<COLLADA>',
          '<library_geometries><geometry id="geom"><mesh>',
          '<source id="pos"><float_array id="pos-array" count="12">0 0 0 1 0 0 1 1 0 0 1 0</float_array>',
          '<technique_common><accessor source="#pos-array" count="4" stride="3"/></technique_common></source>',
          '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
          '<polygons count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2 3</p></polygons>',
          '</mesh></geometry></library_geometries>',
          '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
          '</COLLADA>',
        ].join(''),
      ),
      '',
    );
    assert.equal(getAttributeArray(result.children[0]!.geometry.position).length, 18);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser preserves line primitives as line objects', async () => {
  setupCompiledColladaParser();

  try {
    const result = await parseColladaMeshDataWithWasm(
      new TextEncoder().encode(
        [
          '<COLLADA>',
          '<library_geometries><geometry id="geom"><mesh>',
          '<source id="pos"><float_array id="pos-array" count="12">0 0 0 1 0 0 1 1 0 0 1 0</float_array>',
          '<technique_common><accessor source="#pos-array" count="4" stride="3"/></technique_common></source>',
          '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
          '<triangles count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2</p></triangles>',
          '<lines count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>2 3</p></lines>',
          '</mesh></geometry></library_geometries>',
          '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
          '</COLLADA>',
        ].join(''),
      ),
      '',
    );
    assert.deepEqual(
      result.children.map((child) => child.primitiveKind),
      ['mesh', 'lines'],
    );

    const scene = createSceneFromSerializedColladaData(result);
    assert.equal(collectMeshes(scene).length, 1);
    const lines = scene.children.filter((child) => (child as THREE.LineSegments).isLineSegments);
    assert.equal(lines.length, 1);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser supports transform stacks and nested nodes', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1"><asset><up_axis>Y_UP</up_axis></asset>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="parent">',
      '<translate>1 2 3</translate>',
      '<node id="child"><rotate>0 0 1 90</rotate><scale>2 3 4</scale><instance_geometry url="#geom"/></node>',
      '</node></visual_scene></library_visual_scenes><scene><instance_visual_scene url="#Scene"/></scene>',
      '</COLLADA>',
    ].join('');
    const fastScene = createSceneFromSerializedColladaData(
      await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), ''),
    );
    const slowScene = createSceneFromSerializedColladaData(parseColladaSceneData(text, 'nested.dae'));
    const fastMesh = collectMeshes(fastScene)[0]!;
    const slowMesh = collectMeshes(slowScene)[0]!;

    assert.ok(maxArrayDelta(fastMesh.matrixWorld.elements, slowMesh.matrixWorld.elements) < 1e-6);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser accepts Z_UP metadata like the normalized JS path', async () => {
  setupCompiledColladaParser();

  try {
    const result = await parseColladaMeshDataWithWasm(
      new TextEncoder().encode(
        [
          '<COLLADA>',
          '<asset><up_axis>Z_UP</up_axis></asset>',
          '<library_geometries><geometry id="geom"><mesh>',
          '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
          '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
          '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
          '<triangles count="1"><input semantic="VERTEX" source="#verts" offset="0"/><p>0 1 2</p></triangles>',
          '</mesh></geometry></library_geometries>',
          '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
          '</COLLADA>',
        ].join(''),
      ),
      '',
    );
    assert.equal(result.children.length, 1);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser supports vertex colors and secondary texcoords', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1"><asset><up_axis>Y_UP</up_axis></asset>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<source id="uv0"><float_array id="uv0-array" count="6">0 0 1 0 0 1</float_array>',
      '<technique_common><accessor source="#uv0-array" count="3" stride="2"/></technique_common></source>',
      '<source id="uv1"><float_array id="uv1-array" count="6">0.5 0.5 0.75 0.5 0.5 0.75</float_array>',
      '<technique_common><accessor source="#uv1-array" count="3" stride="2"/></technique_common></source>',
      '<source id="color"><float_array id="color-array" count="12">1 0 0 1 0 1 0 1 0 0 1 1</float_array>',
      '<technique_common><accessor source="#color-array" count="3" stride="4"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1">',
      '<input semantic="VERTEX" source="#verts" offset="0"/>',
      '<input semantic="TEXCOORD" source="#uv0" offset="1" set="0"/>',
      '<input semantic="TEXCOORD" source="#uv1" offset="2" set="1"/>',
      '<input semantic="COLOR" source="#color" offset="3" set="0"/>',
      '<p>0 0 0 0 1 1 1 1 2 2 2 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const fastScene = createSceneFromSerializedColladaData(
      await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), ''),
    );
    const slowScene = createSceneFromSerializedColladaData(parseColladaSceneData(text, 'color-uv1.dae'));
    const fastGeometry = collectMeshes(fastScene)[0]!.geometry;
    const slowGeometry = collectMeshes(slowScene)[0]!.geometry;

    for (const attributeName of ['position', 'uv', 'uv1', 'color']) {
      const fastAttribute = fastGeometry.getAttribute(attributeName)!;
      const slowAttribute = slowGeometry.getAttribute(attributeName)!;
      assert.equal(Boolean(fastAttribute), true, `${attributeName}: fast attribute`);
      assert.equal(fastAttribute.itemSize, slowAttribute.itemSize, `${attributeName}: itemSize`);
      assert.ok(
        maxArrayDelta(fastAttribute.array, slowAttribute.array) < 1e-6,
        `${attributeName}: values differ`,
      );
    }
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser rejects inconsistent polylist data', async () => {
  setupCompiledColladaParser();

  try {
    await assert.rejects(
      parseColladaMeshDataWithWasm(
        new TextEncoder().encode(
          [
            '<COLLADA>',
            '<library_geometries><geometry id="geom"><mesh>',
            '<source id="pos"><float_array id="pos-array" count="12">0 0 0 1 0 0 0 1 0 1 1 0</float_array>',
            '<technique_common><accessor source="#pos-array" count="4" stride="3"/></technique_common></source>',
            '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
            '<polylist count="1"><input semantic="VERTEX" source="#verts" offset="0"/><vcount>3 3</vcount><p>0 1 2 1 2 3</p></polylist>',
            '</mesh></geometry></library_geometries>',
            '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom"/></node></visual_scene></library_visual_scenes>',
            '</COLLADA>',
          ].join(''),
        ),
        '',
      ),
      /polylist count|vcount/i,
    );
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser ignores XML comments inside material parameters', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1">',
      '<!-- top-level comment with fake <library_materials> noise -->',
      '<library_effects><effect id="mat-effect"><profile_COMMON><technique sid="common">',
      '<phong>',
      // Commented-out diffuse should be ignored — the real one is 0.25 0.5 0.75.
      '<diffuse><!-- <color>0 0 0 1</color> --><color>0.25 0.5 0.75 1</color></diffuse>',
      '<!-- <transparent opaque="A_ONE"><color>1 1 1 0</color></transparent> -->',
      '</phong>',
      '</technique></profile_COMMON></effect></library_effects>',
      '<library_materials><material id="mat" name="commented"><instance_effect url="#mat-effect"/></material></library_materials>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1" material="mat-symbol">',
      '<input semantic="VERTEX" source="#verts" offset="0"/>',
      '<p>0 1 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom">',
      '<bind_material><technique_common><instance_material symbol="mat-symbol" target="#mat"/></technique_common></bind_material>',
      '</instance_geometry></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const fastData = await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), '');
    const material = fastData.children[0]!.materials[0]!;
    assert.equal(material.name, 'commented');
    // 0.25 / 0.5 / 0.75 → 0x4080bf (uses linear→hex packing in WASM).
    const r = (material.color >> 16) & 0xff;
    const g = (material.color >> 8) & 0xff;
    const b = material.color & 0xff;
    assert.equal(r, Math.round(0.25 * 255));
    assert.equal(g, Math.round(0.5 * 255));
    assert.equal(b, Math.round(0.75 * 255));
    assert.equal(material.transparent, false);
    assert.equal(material.opacity, 1);
  } finally {
    resetColladaWasmParserForTests();
  }
});

test('compiled Collada mesh WASM parser ignores CDATA inside material parameters', async () => {
  setupCompiledColladaParser();

  try {
    const text = [
      '<COLLADA version="1.4.1">',
      '<library_effects><effect id="mat-effect"><profile_COMMON><technique sid="common">',
      '<phong>',
      '<diffuse><![CDATA[ <color>0 0 0 1</color> ]]><color>1 0 0 1</color></diffuse>',
      '</phong>',
      '</technique></profile_COMMON></effect></library_effects>',
      '<library_materials><material id="mat" name="cdata"><instance_effect url="#mat-effect"/></material></library_materials>',
      '<library_geometries><geometry id="geom"><mesh>',
      '<source id="pos"><float_array id="pos-array" count="9">0 0 0 1 0 0 0 1 0</float_array>',
      '<technique_common><accessor source="#pos-array" count="3" stride="3"/></technique_common></source>',
      '<vertices id="verts"><input semantic="POSITION" source="#pos"/></vertices>',
      '<triangles count="1" material="mat-symbol">',
      '<input semantic="VERTEX" source="#verts" offset="0"/>',
      '<p>0 1 2</p></triangles>',
      '</mesh></geometry></library_geometries>',
      '<library_visual_scenes><visual_scene id="Scene"><node id="node"><instance_geometry url="#geom">',
      '<bind_material><technique_common><instance_material symbol="mat-symbol" target="#mat"/></technique_common></bind_material>',
      '</instance_geometry></node></visual_scene></library_visual_scenes>',
      '<scene><instance_visual_scene url="#Scene"/></scene></COLLADA>',
    ].join('');
    const fastData = await parseColladaMeshDataWithWasm(new TextEncoder().encode(text), '');
    const material = fastData.children[0]!.materials[0]!;
    assert.equal(material.name, 'cdata');
    const r = (material.color >> 16) & 0xff;
    const g = (material.color >> 8) & 0xff;
    const b = material.color & 0xff;
    assert.equal(r, 0xff);
    assert.equal(g, 0);
    assert.equal(b, 0);
  } finally {
    resetColladaWasmParserForTests();
  }
});

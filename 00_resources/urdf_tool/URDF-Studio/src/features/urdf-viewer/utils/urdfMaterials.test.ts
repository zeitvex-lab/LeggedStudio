import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { JSDOM } from 'jsdom';
import { GeometryType, type UrdfLink } from '@/types';

import { applyURDFMaterials, collectURDFMaterialsFromLinks, parseURDFMaterials, resolveURDFMaterialsForScene } from './urdfMaterials';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;

function toFixedColorArray(color: THREE.Color) {
    return color.toArray().map((value) => Number(value.toFixed(4)));
}

test('applyURDFMaterials matches normalized Collada material names from URDF inline materials', () => {
    const materials = parseURDFMaterials(`<?xml version="1.0"?>
<robot name="b2w_description">
  <link name="base_link">
    <visual>
      <geometry>
        <mesh filename="package://b2w_description/meshes/base_link.dae" />
      </geometry>
      <material name="磨砂铝合金_008-effect">
        <color rgba="0.25 0.5 0.75 1" />
      </material>
      <material name="灰色硅胶_009-effect">
        <color rgba="0.1 0.2 0.3 0.5" />
      </material>
      <material name="黑色硅胶-effect">
        <color rgba="0.02 0.03 0.04 1" />
      </material>
    </visual>
  </link>
</robot>`);

    const texture = new THREE.Texture();
    const robot = new THREE.Group();
    const originalMetalMaterial = new THREE.MeshPhongMaterial({
        name: '磨砂铝合金.008',
        color: new THREE.Color(1, 0, 0),
        map: texture,
    });
    const originalRubberMaterial = new THREE.MeshPhongMaterial({
        name: '灰色硅胶.009',
        color: new THREE.Color(0, 1, 0),
    });
    const legMesh = new THREE.Mesh(
        new THREE.BoxGeometry(1, 1, 1),
        [originalMetalMaterial, originalRubberMaterial],
    );
    const originalFootMaterial = new THREE.MeshPhongMaterial({
        name: '黑色硅胶',
        color: new THREE.Color(0, 0, 1),
    });
    const footMesh = new THREE.Mesh(
        new THREE.BoxGeometry(1, 1, 1),
        originalFootMaterial,
    );
    robot.add(legMesh, footMesh);

    applyURDFMaterials(robot, materials);

    const [metalMaterial, rubberMaterial] = legMesh.material as THREE.MeshPhongMaterial[];
    const footMaterial = footMesh.material as THREE.MeshPhongMaterial;

    assert.notEqual(metalMaterial, originalMetalMaterial);
    assert.notEqual(rubberMaterial, originalRubberMaterial);
    assert.notEqual(footMaterial, originalFootMaterial);
    assert.equal(metalMaterial instanceof THREE.MeshPhongMaterial, true);
    assert.equal(rubberMaterial instanceof THREE.MeshPhongMaterial, true);
    assert.equal(footMaterial instanceof THREE.MeshPhongMaterial, true);
    assert.equal(metalMaterial.map, texture);

    assert.equal(metalMaterial.userData.urdfColorApplied, true);
    assert.deepEqual(
        toFixedColorArray(metalMaterial.color),
        toFixedColorArray(new THREE.Color().setRGB(0.25, 0.5, 0.75, THREE.SRGBColorSpace)),
    );

    assert.equal(rubberMaterial.userData.urdfColorApplied, true);
    assert.deepEqual(
        toFixedColorArray(rubberMaterial.color),
        toFixedColorArray(new THREE.Color().setRGB(0.1, 0.2, 0.3, THREE.SRGBColorSpace)),
    );
    assert.equal(Number(rubberMaterial.opacity.toFixed(4)), 0.5);
    assert.equal(rubberMaterial.transparent, true);

    assert.equal(footMaterial.userData.urdfColorApplied, true);
    assert.deepEqual(
        toFixedColorArray(footMaterial.color),
        toFixedColorArray(new THREE.Color().setRGB(0.02, 0.03, 0.04, THREE.SRGBColorSpace)),
    );
});

test('applyURDFMaterials keeps vertex-colored OBJ materials on a neutral material base', () => {
    const materials = new Map([
        [
            'material_____________005',
            { name: 'material_____________005', rgba: [0, 0, 0, 1] as [number, number, number, number] },
        ],
    ]);
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
        'position',
        new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3),
    );
    geometry.setAttribute(
        'color',
        new THREE.Float32BufferAttribute([0.67, 0.69, 0.77, 0.67, 0.69, 0.77, 0, 0, 0], 3),
    );
    const originalMaterial = new THREE.MeshStandardMaterial({
        name: 'material_____________005',
        color: 0x000000,
        vertexColors: true,
    });
    originalMaterial.userData = {
        usesVertexColors: true,
        urdfColorApplied: true,
        urdfColor: new THREE.Color(0x000000),
    };
    const mesh = new THREE.Mesh(geometry, originalMaterial);
    const robot = new THREE.Group();
    robot.add(mesh);

    applyURDFMaterials(robot, materials);

    const appliedMaterial = mesh.material as THREE.MeshStandardMaterial;
    assert.notEqual(appliedMaterial, originalMaterial);
    assert.equal(appliedMaterial.vertexColors, true);
    assert.equal(appliedMaterial.color.getHexString(), 'ffffff');
    assert.equal(appliedMaterial.toneMapped, false);
    assert.equal(appliedMaterial.userData.usesVertexColors, true);
    assert.notEqual(appliedMaterial.userData.urdfColorApplied, true);
    assert.equal(appliedMaterial.userData.urdfColor, undefined);
    assert.equal(appliedMaterial.userData.urdfMaterialName, 'material_____________005');
});

test('applyURDFMaterials interprets unitree-style orange as sRGB instead of linear RGB', () => {
    const materials = parseURDFMaterials(`<?xml version="1.0"?>
<robot name="b1_description">
  <material name="orange">
    <color rgba="1 0.4235294118 0.0392156863 1" />
  </material>
</robot>`);

    const originalMaterial = new THREE.MeshPhongMaterial({
        name: 'orange',
        color: new THREE.Color(1, 1, 1),
    });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), originalMaterial);
    const robot = new THREE.Group();
    robot.add(mesh);

    applyURDFMaterials(robot, materials);

    const appliedMaterial = mesh.material as THREE.MeshPhongMaterial;
    const expected = new THREE.Color().setRGB(1, 0.4235294118, 0.0392156863, THREE.SRGBColorSpace);
    const incorrectLinear = new THREE.Color(1, 0.4235294118, 0.0392156863);

    assert.deepEqual(toFixedColorArray(appliedMaterial.color), toFixedColorArray(expected));
    assert.notDeepEqual(toFixedColorArray(appliedMaterial.color), toFixedColorArray(incorrectLinear));
});

test('collectURDFMaterialsFromLinks reuses authored multi-material palettes without reparsing XML', () => {
    const links: Record<string, UrdfLink> = {
        base_link: {
            id: 'base_link',
            name: 'base_link',
            visual: {
                type: GeometryType.MESH,
                meshPath: 'package://demo/meshes/base.dae',
                dimensions: { x: 1, y: 1, z: 1 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
                authoredMaterials: [
                    { name: 'Orange-effect', color: '#ff6c0a' },
                    { name: 'Rubber-effect', color: '#1a1a1a' },
                ],
            },
            collision: {
                type: GeometryType.NONE,
                dimensions: { x: 0, y: 0, z: 0 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            },
        },
    };

    const materials = collectURDFMaterialsFromLinks(links);

    assert.deepEqual(
        materials.get('Orange-effect')?.rgba?.map((value) => Number(value.toFixed(4))),
        [1, 0.4235, 0.0392, 1],
    );
    assert.deepEqual(
        materials.get('Rubber-effect')?.rgba?.map((value) => Number(value.toFixed(4))),
        [0.102, 0.102, 0.102, 1],
    );
});

test('resolveURDFMaterialsForScene prefers pre-parsed link materials when available', () => {
    const links: Record<string, UrdfLink> = {
        base_link: {
            id: 'base_link',
            name: 'base_link',
            visual: {
                type: GeometryType.MESH,
                meshPath: 'package://demo/meshes/base.dae',
                dimensions: { x: 1, y: 1, z: 1 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
                authoredMaterials: [{ name: 'Orange-effect', color: '#ff6c0a' }],
            },
            collision: {
                type: GeometryType.NONE,
                dimensions: { x: 0, y: 0, z: 0 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            },
        },
    };

    const materials = resolveURDFMaterialsForScene('<robot name="demo" />', links);

    assert.equal(materials.has('Orange-effect'), true);
});

test('resolveURDFMaterialsForScene treats empty source content as no material definitions', () => {
    const materials = resolveURDFMaterialsForScene('', {
        base_link: {
            id: 'base_link',
            name: 'base_link',
            visual: {
                type: GeometryType.BOX,
                dimensions: { x: 1, y: 1, z: 1 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            },
            collision: {
                type: GeometryType.NONE,
                dimensions: { x: 0, y: 0, z: 0 },
                color: '#ffffff',
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            },
        },
    });

    assert.equal(materials.size, 0);
});

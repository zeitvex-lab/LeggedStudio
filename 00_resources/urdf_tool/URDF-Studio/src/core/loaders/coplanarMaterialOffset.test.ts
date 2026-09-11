import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
    isCoplanarOffsetMaterial,
    mitigateCoplanarMaterialZFighting,
} from './coplanarMaterialOffset.ts';

test('mitigateCoplanarMaterialZFighting offsets the smaller overlapping material group', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        0, 0, 1,
    ], 3));
    geometry.setIndex([0, 1, 2, 0, 1, 3, 0, 1, 2]);
    geometry.clearGroups();
    geometry.addGroup(0, 6, 0);
    geometry.addGroup(6, 3, 1);

    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const overlayMaterial = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [baseMaterial, overlayMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 1);
    assert.equal(result.nearCoplanarTriangleCount, 0);
    assert.deepEqual(result.adjustedMaterialIndices, [1]);
    assert.equal(result.adjustedMaterialCount, 1);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), false);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), true);
    assert.notEqual(materials[1], overlayMaterial);
    assert.equal(materials[1].polygonOffset, true);
    assert.equal(materials[1].polygonOffsetFactor, -2);
    assert.equal(materials[1].polygonOffsetUnits, -2);
});

test('mitigateCoplanarMaterialZFighting is a no-op when material groups do not overlap', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        0, 0, 1,
        1, 0, 1,
        0, 1, 1,
    ], 3));
    geometry.clearGroups();
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);

    const materialA = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const materialB = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [materialA, materialB]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 0);
    assert.equal(result.nearCoplanarTriangleCount, 0);
    assert.equal(result.adjustedMaterialCount, 0);
    assert.equal(materials[0], materialA);
    assert.equal(materials[1], materialB);
});

test('mitigateCoplanarMaterialZFighting pushes the more exterior material group ahead for slightly drifted shells', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        0.002, 0.002, 0.0001,
        1.002, 0.002, 0.0001,
        0.002, 1.002, 0.0001,
    ], 3));
    geometry.clearGroups();
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);

    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const overlayMaterial = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [baseMaterial, overlayMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 0);
    assert.equal(result.nearCoplanarTriangleCount, 1);
    assert.deepEqual(result.adjustedMaterialIndices, [0]);
    assert.equal(result.adjustedMaterialCount, 1);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), false);
});

test('mitigateCoplanarMaterialZFighting keeps the innermost near-coplanar material as the anchor', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        -0.002, -0.002, 0.0001,
        1.002, -0.002, 0.0001,
        -0.002, 1.002, 0.0001,
        0, 0, 3,
        1, 0, 3,
        0, 1, 3,
    ], 3));
    geometry.clearGroups();
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 6, 1);

    const innerMaterial = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const outerShellMaterial = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [innerMaterial, outerShellMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 0);
    assert.equal(result.nearCoplanarTriangleCount, 1);
    assert.deepEqual(result.adjustedMaterialIndices, [1]);
    assert.equal(result.adjustedMaterialCount, 1);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), false);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), true);
});

test('mitigateCoplanarMaterialZFighting offsets every more exterior material in an overlapping chain', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        0, 0, 1,
        1, 0, 1,
        0, 1, 1,
        0, 0, 2,
        1, 0, 2,
        0, 1, 2,
        0, 0, 3,
        1, 0, 3,
        0, 1, 3,
        0, 0, 4,
        1, 0, 4,
        0, 1, 4,
        0, 0, 5,
        1, 0, 5,
        0, 1, 5,
        0, 0, 6,
        1, 0, 6,
        0, 1, 6,
    ], 3));
    geometry.setIndex([
        0, 1, 2,
        3, 4, 5,
        6, 7, 8,
        18, 19, 20,
        0, 1, 2,
        12, 13, 14,
        12, 13, 14,
        9, 10, 11,
        15, 16, 17,
    ]);
    geometry.clearGroups();
    geometry.addGroup(0, 12, 0);
    geometry.addGroup(12, 6, 1);
    geometry.addGroup(18, 9, 2);

    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const bridgeMaterial = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const overlayMaterial = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [baseMaterial, bridgeMaterial, overlayMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 2);
    assert.equal(result.nearCoplanarTriangleCount, 0);
    assert.deepEqual(result.adjustedMaterialIndices, [0, 1]);
    assert.equal(result.adjustedMaterialCount, 2);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[2]), false);
});

test('mitigateCoplanarMaterialZFighting keeps a dominant shell material as the anchor over tiny centered decals', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0.0, 0.0, 0.0,
        0.1, 0.0, 0.0,
        0.0, 0.1, 0.0,

        10.0, 0.0, 0.0,
        11.0, 0.0, 0.0,
        10.0, 1.0, 0.0,
    ], 3));
    geometry.setIndex([
        0, 1, 2,
        3, 4, 5,
        3, 4, 5,
        3, 4, 5,
        3, 4, 5,
        3, 4, 5,
        3, 4, 5,
        3, 4, 5,
        0, 1, 2,
        0, 1, 2,
        0, 1, 2,
    ]);
    geometry.clearGroups();
    geometry.addGroup(0, 24, 0);
    geometry.addGroup(24, 6, 1);
    geometry.addGroup(30, 3, 2);

    const shellMaterial = new THREE.MeshStandardMaterial({ color: 0xe0e0e0, name: 'shell' });
    const logoMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, name: 'logo' });
    const accentMaterial = new THREE.MeshStandardMaterial({ color: 0x111111, name: 'accent' });
    const mesh = new THREE.Mesh(geometry, [shellMaterial, logoMaterial, accentMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 1);
    assert.equal(result.adjustedMaterialCount, 2);
    assert.deepEqual(result.adjustedMaterialIndices, [1, 2]);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), false);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[2]), true);
    assert.equal(materials[1].polygonOffsetFactor, -3);
    assert.equal(materials[1].polygonOffsetUnits, -4);
    assert.equal(materials[2].polygonOffsetFactor, -2);
    assert.equal(materials[2].polygonOffsetUnits, -2);
});

test('mitigateCoplanarMaterialZFighting remaps only the overlapping group when a shared material is reused elsewhere', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
        10, 0, 0,
        11, 0, 0,
        10, 1, 0,
    ], 3));
    geometry.setIndex([
        0, 1, 2,
        0, 1, 2,
        0, 1, 2,
        3, 4, 5,
    ]);
    geometry.clearGroups();
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    geometry.addGroup(6, 3, 2);
    geometry.addGroup(9, 3, 1);

    const shellMaterial = new THREE.MeshStandardMaterial({ color: 0xe0e0e0, name: 'shell' });
    const accentMaterial = new THREE.MeshStandardMaterial({ color: 0x111111, name: 'accent' });
    const logoMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, name: 'logo' });
    const mesh = new THREE.Mesh(geometry, [shellMaterial, accentMaterial, logoMaterial]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 1);
    assert.equal(result.adjustedMaterialCount, 2);
    assert.deepEqual(result.adjustedMaterialIndices, [1, 2]);
    assert.equal(materials.length, 4);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), false);
    assert.equal(isCoplanarOffsetMaterial(materials[2]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[3]), true);
    assert.equal(materials[2].polygonOffsetFactor, -3);
    assert.equal(materials[2].polygonOffsetUnits, -4);
    assert.equal(materials[3].polygonOffsetFactor, -2);
    assert.equal(materials[3].polygonOffsetUnits, -2);
    assert.equal(mesh.geometry.groups[0]?.materialIndex, 0);
    assert.equal(mesh.geometry.groups[1]?.materialIndex, 3);
    assert.equal(mesh.geometry.groups[2]?.materialIndex, 2);
    assert.equal(mesh.geometry.groups[3]?.materialIndex, 1);
});

test('mitigateCoplanarMaterialZFighting assigns progressive offsets for stacked duplicate overlays', () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute([
        0, 0, 0,
        1, 0, 0,
        0, 1, 0,
    ], 3));
    geometry.setIndex([
        0, 1, 2,
        0, 1, 2,
        0, 1, 2,
    ]);
    geometry.clearGroups();
    geometry.addGroup(0, 3, 0);
    geometry.addGroup(3, 3, 1);
    geometry.addGroup(6, 3, 2);

    const baseMaterial = new THREE.MeshStandardMaterial({ color: 0x999999 });
    const overlayMaterialA = new THREE.MeshStandardMaterial({ color: 0x222222 });
    const overlayMaterialB = new THREE.MeshStandardMaterial({ color: 0x111111 });
    const mesh = new THREE.Mesh(geometry, [baseMaterial, overlayMaterialA, overlayMaterialB]);

    const result = mitigateCoplanarMaterialZFighting(mesh);
    const materials = mesh.material as THREE.Material[];

    assert.equal(result.duplicateTriangleCount, 1);
    assert.equal(result.nearCoplanarTriangleCount, 0);
    assert.deepEqual(result.adjustedMaterialIndices, [1, 2]);
    assert.equal(result.adjustedMaterialCount, 2);
    assert.equal(isCoplanarOffsetMaterial(materials[0]), false);
    assert.equal(isCoplanarOffsetMaterial(materials[1]), true);
    assert.equal(isCoplanarOffsetMaterial(materials[2]), true);
    assert.equal(materials[1].polygonOffsetFactor, -2);
    assert.equal(materials[1].polygonOffsetUnits, -2);
    assert.equal(materials[2].polygonOffsetFactor, -3);
    assert.equal(materials[2].polygonOffsetUnits, -4);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  createObjectFromSerializedObjData,
  createObjectFromSerializedObjDataAsync,
  type SerializedObjModelData,
} from './objModelData.ts';

function floatBuffer(values: number[]): ArrayBuffer {
  return new Float32Array(values).buffer;
}

test('createObjectFromSerializedObjData forces vertex colors when OBJ geometry carries color attributes', () => {
  const serialized: SerializedObjModelData = {
    materialLibraries: [],
    children: [
      {
        kind: 'mesh',
        name: 'colored-mesh',
        materials: [
          {
            kind: 'mesh-phong',
            name: 'default',
            color: 0xffffff,
            vertexColors: false,
          },
        ],
        geometry: {
          position: {
            array: floatBuffer([
              0, 0, 0,
              1, 0, 0,
              0, 1, 0,
            ]),
            itemSize: 3,
          },
          color: {
            array: floatBuffer([
              1, 0, 0,
              0, 1, 0,
              0, 0, 1,
            ]),
            itemSize: 3,
          },
          groups: [],
        },
      },
    ],
  };

  const object = createObjectFromSerializedObjData(serialized);
  const mesh = object.children[0] as THREE.Mesh;

  assert.ok(mesh.isMesh);
  assert.ok(mesh.geometry.getAttribute('color'));
  assert.ok(mesh.material instanceof THREE.MeshPhongMaterial);

  if (!(mesh.material instanceof THREE.MeshPhongMaterial)) {
    assert.fail('expected a MeshPhongMaterial');
  }

  assert.equal(mesh.material.vertexColors, true);
});

test('createObjectFromSerializedObjData uses a neutral base for vertex-colored OBJ materials', () => {
  const serialized: SerializedObjModelData = {
    materialLibraries: [],
    children: [
      {
        kind: 'mesh',
        name: 'calf',
        materials: [
          {
            kind: 'mesh-phong',
            name: 'black_patch',
            color: 0x000000,
            vertexColors: false,
          },
        ],
        geometry: {
          position: {
            array: floatBuffer([
              0, 0, 0,
              1, 0, 0,
              0, 1, 0,
            ]),
            itemSize: 3,
          },
          color: {
            array: floatBuffer([
              0.67, 0.69, 0.77,
              0.67, 0.69, 0.77,
              0, 0, 0,
            ]),
            itemSize: 3,
          },
          groups: [],
        },
      },
    ],
  };

  const object = createObjectFromSerializedObjData(serialized);
  const mesh = object.children[0] as THREE.Mesh;
  const material = mesh.material as THREE.MeshPhongMaterial;

  assert.equal(material.vertexColors, true);
  assert.equal(material.color.getHexString(), 'ffffff');
  assert.equal(material.toneMapped, false);
  assert.equal(material.userData.usesVertexColors, true);
});

test('createObjectFromSerializedObjDataAsync yields while assembling multi-node OBJ scenes', async () => {
  const makeChild = (name: string): SerializedObjModelData['children'][number] => ({
    kind: 'mesh',
    name,
    materials: [
      {
        kind: 'mesh-phong',
        name: 'default',
        color: 0xffffff,
        vertexColors: false,
      },
    ],
    geometry: {
      position: {
        array: floatBuffer([
          0, 0, 0,
          1, 0, 0,
          0, 1, 0,
        ]),
        itemSize: 3,
      },
      groups: [],
    },
  });
  const serialized: SerializedObjModelData = {
    materialLibraries: ['robot.mtl'],
    children: [makeChild('a'), makeChild('b'), makeChild('c')],
  };
  let yieldCount = 0;

  const object = await createObjectFromSerializedObjDataAsync(serialized, {
    nodeYieldInterval: 1,
    yieldIfNeeded: async () => {
      yieldCount += 1;
    },
  });

  assert.equal(object.children.length, 3);
  assert.deepEqual(
    (object as THREE.Group & { materialLibraries?: string[] }).materialLibraries,
    ['robot.mtl'],
  );
  assert.equal(yieldCount, 4);
});

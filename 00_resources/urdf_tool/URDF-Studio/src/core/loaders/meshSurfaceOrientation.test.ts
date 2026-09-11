import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import * as THREE from 'three';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';

import {
  isLikelyThinSheetGeometry,
  prepareMeshSurfaceForSingleSidedRendering,
} from './meshSurfaceOrientation.ts';

function outwardFacingTriangleRatio(geometry: THREE.BufferGeometry): number {
  const position = geometry.getAttribute('position');
  assert.ok(position);

  const index = geometry.getIndex();
  const centroid = new THREE.Vector3();
  const vertex = new THREE.Vector3();

  for (let vertexIndex = 0; vertexIndex < position.count; vertexIndex += 1) {
    vertex.fromBufferAttribute(position, vertexIndex);
    centroid.add(vertex);
  }
  centroid.multiplyScalar(1 / position.count);

  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const ab = new THREE.Vector3();
  const ac = new THREE.Vector3();
  const normal = new THREE.Vector3();
  const faceCenter = new THREE.Vector3();

  let outwardCount = 0;
  let triangleCount = 0;
  const triangleVertexCount = index ? index.count : position.count;
  for (let triangleOffset = 0; triangleOffset <= triangleVertexCount - 3; triangleOffset += 3) {
    const ia = index ? index.getX(triangleOffset) : triangleOffset;
    const ib = index ? index.getX(triangleOffset + 1) : triangleOffset + 1;
    const ic = index ? index.getX(triangleOffset + 2) : triangleOffset + 2;

    a.fromBufferAttribute(position, ia);
    b.fromBufferAttribute(position, ib);
    c.fromBufferAttribute(position, ic);
    ab.subVectors(b, a);
    ac.subVectors(c, a);
    normal.crossVectors(ab, ac);
    if (normal.lengthSq() <= 1e-9) {
      continue;
    }

    faceCenter.copy(a).add(b).add(c).multiplyScalar(1 / 3).sub(centroid);
    if (normal.dot(faceCenter) >= 0) {
      outwardCount += 1;
    }
    triangleCount += 1;
  }

  return triangleCount > 0 ? outwardCount / triangleCount : 1;
}

function swapIndexedTriangleWinding(geometry: THREE.BufferGeometry, triangleOffset: number): void {
  const index = geometry.getIndex();
  assert.ok(index);
  const left = index.getX(triangleOffset + 1);
  const right = index.getX(triangleOffset + 2);
  index.setX(triangleOffset + 1, right);
  index.setX(triangleOffset + 2, left);
  index.needsUpdate = true;
}

function swapNonIndexedTriangleWinding(geometry: THREE.BufferGeometry, triangleOffset: number): void {
  const attributes = Object.values(geometry.attributes);
  for (const attribute of attributes) {
    for (let component = 0; component < attribute.itemSize; component += 1) {
      const left = attribute.getComponent(triangleOffset + 1, component);
      const right = attribute.getComponent(triangleOffset + 2, component);
      attribute.setComponent(triangleOffset + 1, component, right);
      attribute.setComponent(triangleOffset + 2, component, left);
    }
    attribute.needsUpdate = true;
  }
}

function createParallelOpenShellGeometry(): THREE.BufferGeometry {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array([
    -1, -1, -1,
    -1, 1, -1,
    -1, 1, 1,
    -1, -1, -1,
    -1, 1, 1,
    -1, -1, 1,
    1, -1, -1,
    1, 1, -1,
    1, 1, 1,
    1, -1, -1,
    1, 1, 1,
    1, -1, 1,
  ]);
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function weldGeometryVertices(geometry: THREE.BufferGeometry): {
  vertices: Array<[number, number, number]>;
  faces: Array<[number, number, number]>;
} {
  const position = geometry.getAttribute('position');
  assert.ok(position);

  const index = geometry.getIndex();
  const weldedVertices: Array<[number, number, number]> = [];
  const remappedVertexIndices = new Array<number>(position.count);
  const vertexLookup = new Map<string, number>();
  const triangleVertexCount = index ? index.count : position.count;
  const faces: Array<[number, number, number]> = [];

  const vertex = new THREE.Vector3();
  const makeKey = (input: THREE.Vector3) => (
    `${input.x.toFixed(8)}|${input.y.toFixed(8)}|${input.z.toFixed(8)}`
  );

  for (let vertexIndex = 0; vertexIndex < position.count; vertexIndex += 1) {
    vertex.fromBufferAttribute(position, vertexIndex);
    const key = makeKey(vertex);
    let weldedIndex = vertexLookup.get(key);
    if (weldedIndex == null) {
      weldedIndex = weldedVertices.length;
      weldedVertices.push([vertex.x, vertex.y, vertex.z]);
      vertexLookup.set(key, weldedIndex);
    }
    remappedVertexIndices[vertexIndex] = weldedIndex;
  }

  for (let triangleOffset = 0; triangleOffset <= triangleVertexCount - 3; triangleOffset += 3) {
    const ia = index ? index.getX(triangleOffset) : triangleOffset;
    const ib = index ? index.getX(triangleOffset + 1) : triangleOffset + 1;
    const ic = index ? index.getX(triangleOffset + 2) : triangleOffset + 2;
    faces.push([
      remappedVertexIndices[ia]!,
      remappedVertexIndices[ib]!,
      remappedVertexIndices[ic]!,
    ]);
  }

  return {
    vertices: weldedVertices,
    faces,
  };
}

function hasConsistentWatertightOrientation(geometry: THREE.BufferGeometry): boolean {
  const { faces } = weldGeometryVertices(geometry);
  const edgeToFaces = new Map<string, Array<{ faceIndex: number; edge: [number, number] }>>();

  faces.forEach((face, faceIndex) => {
    const orientedEdges: Array<[number, number]> = [
      [face[0], face[1]],
      [face[1], face[2]],
      [face[2], face[0]],
    ];

    orientedEdges.forEach((edge) => {
      const key = edge[0] < edge[1] ? `${edge[0]}:${edge[1]}` : `${edge[1]}:${edge[0]}`;
      const existing = edgeToFaces.get(key);
      if (existing) {
        existing.push({ faceIndex, edge });
      } else {
        edgeToFaces.set(key, [{ faceIndex, edge }]);
      }
    });
  });

  const adjacency = new Map<number, Array<{ neighborFaceIndex: number; sameDirection: boolean }>>();
  for (let faceIndex = 0; faceIndex < faces.length; faceIndex += 1) {
    adjacency.set(faceIndex, []);
  }

  for (const usages of edgeToFaces.values()) {
    if (usages.length !== 2) {
      return false;
    }

    const [left, right] = usages;
    const sameDirection = left.edge[0] === right.edge[0] && left.edge[1] === right.edge[1];
    adjacency.get(left.faceIndex)!.push({
      neighborFaceIndex: right.faceIndex,
      sameDirection,
    });
    adjacency.get(right.faceIndex)!.push({
      neighborFaceIndex: left.faceIndex,
      sameDirection,
    });
  }

  const orientationState = new Array<number | null>(faces.length).fill(null);
  const queue: number[] = [0];
  orientationState[0] = 1;

  while (queue.length > 0) {
    const faceIndex = queue.shift()!;
    const neighbors = adjacency.get(faceIndex) ?? [];
    for (const neighbor of neighbors) {
      const expectedOrientation = neighbor.sameDirection
        ? -orientationState[faceIndex]!
        : orientationState[faceIndex]!;

      if (orientationState[neighbor.neighborFaceIndex] == null) {
        orientationState[neighbor.neighborFaceIndex] = expectedOrientation;
        queue.push(neighbor.neighborFaceIndex);
        continue;
      }

      if (orientationState[neighbor.neighborFaceIndex] !== expectedOrientation) {
        return false;
      }
    }
  }

  return orientationState.every((value) => value != null);
}

test('prepareMeshSurfaceForSingleSidedRendering repairs mixed winding in indexed geometry', () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  swapIndexedTriangleWinding(geometry, 0);

  const beforeRatio = outwardFacingTriangleRatio(geometry);
  assert.ok(beforeRatio < 1, `expected mixed winding before repair, got ${beforeRatio}`);

  const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial());
  const root = new THREE.Group();
  root.add(mesh);

  const summary = prepareMeshSurfaceForSingleSidedRendering(root);

  assert.ok(summary.flippedTriangleCount > 0);
  assert.equal(summary.repairedMeshCount, 1);
  assert.equal(outwardFacingTriangleRatio(geometry), 1);
  assert.equal(mesh.userData.mjcfPreferDoubleSide, false);
});

test('prepareMeshSurfaceForSingleSidedRendering repairs mixed winding in non-indexed geometry', () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1).toNonIndexed();
  swapNonIndexedTriangleWinding(geometry, 0);

  const beforeRatio = outwardFacingTriangleRatio(geometry);
  assert.ok(beforeRatio < 1, `expected mixed winding before repair, got ${beforeRatio}`);

  const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial());
  const root = new THREE.Group();
  root.add(mesh);

  const summary = prepareMeshSurfaceForSingleSidedRendering(root);

  assert.ok(summary.flippedTriangleCount > 0);
  assert.equal(summary.repairedMeshCount, 1);
  assert.equal(outwardFacingTriangleRatio(geometry), 1);
});

test('isLikelyThinSheetGeometry keeps thin plates double-sided', () => {
  const thinPlate = new THREE.BoxGeometry(2, 1, 0.01);
  const thickShell = new THREE.BoxGeometry(2, 1, 0.2);

  assert.equal(isLikelyThinSheetGeometry(thinPlate), true);
  assert.equal(isLikelyThinSheetGeometry(thickShell), false);

  const mesh = new THREE.Mesh(thinPlate, new THREE.MeshStandardMaterial());
  const root = new THREE.Group();
  root.add(mesh);
  prepareMeshSurfaceForSingleSidedRendering(root);

  assert.equal(mesh.userData.mjcfPreferDoubleSide, true);
});

test('prepareMeshSurfaceForSingleSidedRendering skips ambiguous open shells', () => {
  const geometry = createParallelOpenShellGeometry();
  const beforeRatio = outwardFacingTriangleRatio(geometry);
  assert.equal(beforeRatio, 0.5);

  const mesh = new THREE.Mesh(geometry, new THREE.MeshStandardMaterial());
  const root = new THREE.Group();
  root.add(mesh);

  const summary = prepareMeshSurfaceForSingleSidedRendering(root);

  assert.equal(summary.flippedTriangleCount, 0);
  assert.equal(summary.repairedMeshCount, 0);
  assert.equal(outwardFacingTriangleRatio(geometry), 0.5);
});

test('prepareMeshSurfaceForSingleSidedRendering does not rewrite already consistent concave MJCF mesh fixtures', () => {
  const fixturePath = path.resolve('test/mujoco_menagerie-main/flybody/assets/femur_T1_left_body.obj');
  const object = new OBJLoader().parse(fs.readFileSync(fixturePath, 'utf8'));
  let mesh: THREE.Mesh | null = null as THREE.Mesh | null;

  object.traverse((child: any) => {
    if (!mesh && child?.isMesh) {
      mesh = child;
    }
  });

  assert.ok(mesh, 'expected the flybody fixture to produce a mesh');
  assert.equal(hasConsistentWatertightOrientation(mesh.geometry), true);

  const summary = prepareMeshSurfaceForSingleSidedRendering(object);

  assert.equal(summary.flippedTriangleCount, 0);
  assert.equal(summary.repairedMeshCount, 0);
  assert.equal(Boolean(mesh.userData.mjcfPreferDoubleSide), false);
});

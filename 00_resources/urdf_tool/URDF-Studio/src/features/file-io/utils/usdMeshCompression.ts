import * as THREE from 'three';

import { compressMesh } from '@/core/stl-compressor/meshCompressor.ts';
import { calculateBoundingBox } from '@/core/stl-compressor/stlParser.ts';
import type { STLMeshData } from '@/core/stl-compressor/types.ts';

import { isUsdMeshObject } from './usdMaterialNormalization.ts';

const createGeometryCompressionMeshData = (
  geometry: THREE.BufferGeometry,
): { meshData: STLMeshData; workingGeometry: THREE.BufferGeometry } | null => {
  const workingGeometry = geometry.index ? geometry.toNonIndexed() : geometry.clone();
  const position = workingGeometry.getAttribute('position');
  if (!position || position.count < 3 || position.count % 3 !== 0) {
    workingGeometry.dispose();
    return null;
  }

  if (!workingGeometry.getAttribute('normal')) {
    workingGeometry.computeVertexNormals();
  }

  const normal = workingGeometry.getAttribute('normal');
  if (!normal || normal.count !== position.count) {
    workingGeometry.dispose();
    return null;
  }

  const vertices = new Float32Array(position.count * 3);
  const normals = new Float32Array(normal.count * 3);
  for (let index = 0; index < position.count; index += 1) {
    const offset = index * 3;
    vertices[offset] = position.getX(index);
    vertices[offset + 1] = position.getY(index);
    vertices[offset + 2] = position.getZ(index);
    normals[offset] = normal.getX(index);
    normals[offset + 1] = normal.getY(index);
    normals[offset + 2] = normal.getZ(index);
  }

  const triangleCount = position.count / 3;
  const fileSize = 84 + triangleCount * 50;

  return {
    meshData: {
      filename: 'usd-export-mesh.stl',
      fileSize,
      triangleCount,
      vertices,
      normals,
      boundingBox: calculateBoundingBox(vertices),
      isCompressed: false,
      originalTriangleCount: triangleCount,
      originalFileSize: fileSize,
    },
    workingGeometry,
  };
};

const simplifyGeometryForUsd = (
  geometry: THREE.BufferGeometry,
  quality: number,
): THREE.BufferGeometry | null => {
  const compressionInput = createGeometryCompressionMeshData(geometry);
  if (!compressionInput) {
    return null;
  }

  const { meshData, workingGeometry } = compressionInput;

  try {
    const compressed = compressMesh(meshData, quality);
    if (compressed.triangleCount >= meshData.triangleCount || compressed.vertices.length === 0) {
      return null;
    }

    const simplified = new THREE.BufferGeometry();
    simplified.setAttribute('position', new THREE.BufferAttribute(compressed.vertices.slice(), 3));
    simplified.setAttribute('normal', new THREE.BufferAttribute(compressed.normals.slice(), 3));
    simplified.computeBoundingBox();
    simplified.computeBoundingSphere();
    return simplified;
  } finally {
    workingGeometry.dispose();
  }
};

export const applyUsdMeshCompression = (object: THREE.Object3D, quality: number): void => {
  if (!(quality > 0 && quality < 100)) {
    return;
  }

  const simplifiedGeometries = new Map<THREE.BufferGeometry, THREE.BufferGeometry | null>();

  object.traverse((child) => {
    if (!isUsdMeshObject(child)) {
      return;
    }

    const originalGeometry = child.geometry;
    if (!simplifiedGeometries.has(originalGeometry)) {
      const simplified = simplifyGeometryForUsd(originalGeometry, quality);
      simplifiedGeometries.set(originalGeometry, simplified);
      if (simplified) {
        originalGeometry.dispose();
      }
    }

    const simplifiedGeometry = simplifiedGeometries.get(originalGeometry);
    if (simplifiedGeometry) {
      child.geometry = simplifiedGeometry;
    }
  });
};

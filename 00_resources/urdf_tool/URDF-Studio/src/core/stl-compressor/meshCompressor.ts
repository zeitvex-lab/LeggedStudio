/**
 * Mesh Compressor - Simplify STL meshes via vertex clustering
 * TypeScript rewrite of mesh-compressor.js from stl_compressor_web
 */

import type { STLMeshData } from './types.ts';
import { calculateBoundingBox } from './stlParser.ts';

// ---------------------------------------------------------------------------
// Vertex-clustering simplification
// ---------------------------------------------------------------------------

interface ClusterResult {
  vertices: Float32Array;
  normals: Float32Array;
  triangleCount: number;
}

/**
 * Simplify a mesh using spatial vertex clustering.
 * Vertices that fall in the same grid cell are merged into their centroid.
 * Degenerate triangles (all three vertices in the same cluster) are dropped.
 *
 * @param vertices - Source vertex data (flat, length = triangleCount * 9)
 * @param normals  - Source normal data (same layout as vertices)
 * @param triangleCount - Number of triangles in source
 * @param targetCount   - Desired output triangle count
 * @param boundingBox   - Bounding box of source mesh
 */
function vertexClusteringSimplify(
  vertices: Float32Array,
  normals: Float32Array,
  targetCount: number,
  boundingBox: STLMeshData['boundingBox'],
): ClusterResult {
  const { size, min } = boundingBox;

  // Choose grid resolution so the expected cluster count ~ targetCount
  const cellCount = Math.cbrt(targetCount);
  const cellSizeX = (size[0] || 1) / cellCount;
  const cellSizeY = (size[1] || 1) / cellCount;
  const cellSizeZ = (size[2] || 1) / cellCount;

  // centroid accumulator: [sumX, sumY, sumZ, count]
  const clusterCentroids: number[][] = [];
  // normal accumulator: [sumNx, sumNy, sumNz]
  const clusterNormals: number[][] = [];
  const clusterMap = new Map<string, number>();

  for (let i = 0; i < vertices.length; i += 3) {
    const x = vertices[i];
    const y = vertices[i + 1];
    const z = vertices[i + 2];

    const cx = Math.floor((x - min[0]) / cellSizeX);
    const cy = Math.floor((y - min[1]) / cellSizeY);
    const cz = Math.floor((z - min[2]) / cellSizeZ);
    const key = `${cx},${cy},${cz}`;

    let idx = clusterMap.get(key);
    if (idx === undefined) {
      idx = clusterCentroids.length;
      clusterMap.set(key, idx);
      clusterCentroids.push([x, y, z, 1]);
      clusterNormals.push([normals[i], normals[i + 1], normals[i + 2]]);
    } else {
      clusterCentroids[idx][0] += x;
      clusterCentroids[idx][1] += y;
      clusterCentroids[idx][2] += z;
      clusterCentroids[idx][3] += 1;
      clusterNormals[idx][0] += normals[i];
      clusterNormals[idx][1] += normals[i + 1];
      clusterNormals[idx][2] += normals[i + 2];
    }
  }

  // Finalize centroids and normalize accumulated normals
  const clusterCount = clusterCentroids.length;
  for (let i = 0; i < clusterCount; i++) {
    const count = clusterCentroids[i][3];
    clusterCentroids[i][0] /= count;
    clusterCentroids[i][1] /= count;
    clusterCentroids[i][2] /= count;

    const nx = clusterNormals[i][0];
    const ny = clusterNormals[i][1];
    const nz = clusterNormals[i][2];
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    clusterNormals[i][0] = nx / len;
    clusterNormals[i][1] = ny / len;
    clusterNormals[i][2] = nz / len;
  }

  // Rebuild triangle list, skipping degenerate faces
  const newVertices: number[] = [];
  const newNormals: number[] = [];

  for (let i = 0; i < vertices.length; i += 9) {
    const triIndices: number[] = [];

    for (let j = 0; j < 3; j++) {
      const x = vertices[i + j * 3];
      const y = vertices[i + j * 3 + 1];
      const z = vertices[i + j * 3 + 2];

      const cx = Math.floor((x - min[0]) / cellSizeX);
      const cy = Math.floor((y - min[1]) / cellSizeY);
      const cz = Math.floor((z - min[2]) / cellSizeZ);
      const key = `${cx},${cy},${cz}`;

      triIndices.push(clusterMap.get(key)!);
    }

    // Drop degenerate triangles
    if (
      triIndices[0] === triIndices[1] ||
      triIndices[1] === triIndices[2] ||
      triIndices[0] === triIndices[2]
    ) {
      continue;
    }

    for (let j = 0; j < 3; j++) {
      const idx = triIndices[j];
      newVertices.push(
        clusterCentroids[idx][0],
        clusterCentroids[idx][1],
        clusterCentroids[idx][2],
      );
      newNormals.push(
        clusterNormals[idx][0],
        clusterNormals[idx][1],
        clusterNormals[idx][2],
      );
    }
  }

  return {
    vertices: new Float32Array(newVertices),
    normals: new Float32Array(newNormals),
    triangleCount: newVertices.length / 9,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Compress an STLMeshData to a target quality level.
 *
 * @param meshData - Input mesh (may itself be a previously compressed result)
 * @param quality  - 10–100; 100 means no compression
 * @returns A new STLMeshData (original data preserved for re-compression)
 */
export function compressMesh(meshData: STLMeshData, quality: number): STLMeshData {
  // Always compress from the original, not from a previously compressed version
  const srcVertices = meshData.originalVertices ?? meshData.vertices;
  const srcNormals  = meshData.originalNormals  ?? meshData.normals;
  const srcTriangleCount = meshData.originalTriangleCount;

  const targetCount = Math.max(10, Math.floor(srcTriangleCount * (quality / 100)));

  if (targetCount >= srcTriangleCount) {
    // Quality is effectively 100% – return unmodified original
    return {
      ...meshData,
      vertices: srcVertices,
      normals: srcNormals,
      triangleCount: srcTriangleCount,
      boundingBox: calculateBoundingBox(srcVertices),
      isCompressed: false,
    };
  }

  const result = vertexClusteringSimplify(
    srcVertices,
    srcNormals,
    targetCount,
    meshData.boundingBox,
  );

  const newFileSize = 84 + result.triangleCount * 50;

  return {
    filename: meshData.filename,
    fileSize: newFileSize,
    triangleCount: result.triangleCount,
    vertices: result.vertices,
    normals: result.normals,
    boundingBox: calculateBoundingBox(result.vertices),
    isCompressed: true,
    originalTriangleCount: srcTriangleCount,
    originalFileSize: meshData.originalFileSize,
    originalVertices: srcVertices,
    originalNormals: srcNormals,
    compressionRatio: (1 - result.triangleCount / srcTriangleCount) * 100,
  };
}

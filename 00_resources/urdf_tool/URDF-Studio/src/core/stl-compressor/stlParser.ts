/**
 * STL Parser - Parse ASCII and Binary STL files, serialize to Binary STL
 * TypeScript rewrite of stl-parser.js from stl_compressor_web
 */

import type { STLMeshData, BoundingBox } from './types.ts';

// ---------------------------------------------------------------------------
// Format detection
// ---------------------------------------------------------------------------

/**
 * Heuristic to decide if an ArrayBuffer contains ASCII STL data.
 * Binary STLs may also start with "solid" in their 80-byte header, so we
 * additionally verify that the expected byte-count for a binary file does
 * NOT match the buffer size (a common cross-check).
 */
function isASCII(buffer: ArrayBuffer): boolean {
  const uint8 = new Uint8Array(buffer);
  const firstBytes = String.fromCharCode(...Array.from(uint8.slice(0, 5)));
  if (!firstBytes.toLowerCase().startsWith('solid')) return false;

  // Binary STL: 80-byte header + 4-byte count + 50 bytes * triangleCount
  if (buffer.byteLength < 84) return true;
  const dataView = new DataView(buffer);
  const triangleCount = dataView.getUint32(80, true);
  const expectedBinarySize = 84 + triangleCount * 50;
  // If sizes match it's almost certainly binary
  return buffer.byteLength !== expectedBinarySize;
}

// ---------------------------------------------------------------------------
// ASCII parser
// ---------------------------------------------------------------------------

function parseASCII(buffer: ArrayBuffer, filename: string): STLMeshData {
  const text = new TextDecoder('utf-8').decode(buffer);
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const verticesArr: number[] = [];
  const normalsArr: number[] = [];
  let currentNormal: [number, number, number] = [0, 0, 1];
  const currentFacet: [number, number, number][] = [];

  for (const line of lines) {
    const lower = line.toLowerCase();

    if (lower.startsWith('facet normal')) {
      const parts = lower.split(/\s+/);
      currentNormal = [
        parseFloat(parts[2]),
        parseFloat(parts[3]),
        parseFloat(parts[4]),
      ];
    } else if (lower.startsWith('vertex')) {
      const parts = lower.split(/\s+/);
      currentFacet.push([
        parseFloat(parts[1]),
        parseFloat(parts[2]),
        parseFloat(parts[3]),
      ]);
    } else if (lower.startsWith('endfacet')) {
      if (currentFacet.length === 3) {
        for (const v of currentFacet) {
          verticesArr.push(v[0], v[1], v[2]);
          normalsArr.push(...currentNormal);
        }
      }
      currentFacet.length = 0;
    }
  }

  return createMeshData(
    new Float32Array(verticesArr),
    new Float32Array(normalsArr),
    filename,
    buffer.byteLength,
  );
}

// ---------------------------------------------------------------------------
// Binary parser
// ---------------------------------------------------------------------------

function parseBinary(buffer: ArrayBuffer, filename: string): STLMeshData {
  const dataView = new DataView(buffer);
  let offset = 80; // skip 80-byte header

  const triangleCount = dataView.getUint32(offset, true);
  offset += 4;

  const vertices = new Float32Array(triangleCount * 9);
  const normals = new Float32Array(triangleCount * 9);
  let vi = 0;
  let ni = 0;

  for (let i = 0; i < triangleCount; i++) {
    const nx = dataView.getFloat32(offset, true);
    const ny = dataView.getFloat32(offset + 4, true);
    const nz = dataView.getFloat32(offset + 8, true);
    offset += 12;

    for (let j = 0; j < 3; j++) {
      vertices[vi++] = dataView.getFloat32(offset, true);
      vertices[vi++] = dataView.getFloat32(offset + 4, true);
      vertices[vi++] = dataView.getFloat32(offset + 8, true);
      normals[ni++] = nx;
      normals[ni++] = ny;
      normals[ni++] = nz;
      offset += 12;
    }

    offset += 2; // attribute byte count
  }

  return createMeshData(vertices, normals, filename, buffer.byteLength);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function calculateBoundingBox(vertices: Float32Array): BoundingBox {
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;

  for (let i = 0; i < vertices.length; i += 3) {
    const x = vertices[i];
    const y = vertices[i + 1];
    const z = vertices[i + 2];
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }

  return {
    min: [minX, minY, minZ],
    max: [maxX, maxY, maxZ],
    size: [maxX - minX, maxY - minY, maxZ - minZ],
    center: [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2],
  };
}

function createMeshData(
  vertices: Float32Array,
  normals: Float32Array,
  filename: string,
  fileSize: number,
): STLMeshData {
  const triangleCount = vertices.length / 9;
  return {
    filename,
    fileSize,
    triangleCount,
    vertices,
    normals,
    boundingBox: calculateBoundingBox(vertices),
    isCompressed: false,
    originalTriangleCount: triangleCount,
    originalFileSize: fileSize,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Parse an STL ArrayBuffer (ASCII or Binary) into STLMeshData.
 */
export function parseSTL(buffer: ArrayBuffer, filename = 'mesh.stl'): STLMeshData {
  if (isASCII(buffer)) {
    return parseASCII(buffer, filename);
  }
  return parseBinary(buffer, filename);
}

/**
 * Serialize STLMeshData back to a binary STL ArrayBuffer.
 * Normals are recomputed from the triangle vertices for correctness.
 */
export function serializeToBinarySTL(mesh: STLMeshData): ArrayBuffer {
  const { vertices, triangleCount } = mesh;

  // 80-byte header + 4-byte count + 50 bytes per triangle
  const buffer = new ArrayBuffer(84 + triangleCount * 50);
  const dataView = new DataView(buffer);

  // Header (80 bytes) – write a short ASCII description
  const headerText = new TextEncoder().encode('Binary STL - URDF Studio STL Compressor');
  for (let i = 0; i < 80; i++) {
    dataView.setUint8(i, headerText[i] ?? 0);
  }

  dataView.setUint32(80, triangleCount, true);
  let offset = 84;

  for (let i = 0; i < vertices.length; i += 9) {
    // Recompute face normal
    const ax = vertices[i + 3] - vertices[i];
    const ay = vertices[i + 4] - vertices[i + 1];
    const az = vertices[i + 5] - vertices[i + 2];
    const bx = vertices[i + 6] - vertices[i];
    const by = vertices[i + 7] - vertices[i + 1];
    const bz = vertices[i + 8] - vertices[i + 2];

    let nx = ay * bz - az * by;
    let ny = az * bx - ax * bz;
    let nz = ax * by - ay * bx;
    const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    nx /= len;
    ny /= len;
    nz /= len;

    dataView.setFloat32(offset, nx, true);
    dataView.setFloat32(offset + 4, ny, true);
    dataView.setFloat32(offset + 8, nz, true);
    offset += 12;

    for (let j = 0; j < 3; j++) {
      dataView.setFloat32(offset, vertices[i + j * 3], true);
      dataView.setFloat32(offset + 4, vertices[i + j * 3 + 1], true);
      dataView.setFloat32(offset + 8, vertices[i + j * 3 + 2], true);
      offset += 12;
    }

    offset += 2; // attribute byte count = 0
  }

  return buffer;
}

export { calculateBoundingBox };

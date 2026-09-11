/**
 * STL Compressor - Type Definitions
 */

/** Bounding box of a mesh */
export interface BoundingBox {
  min: [number, number, number];
  max: [number, number, number];
  size: [number, number, number];
  center: [number, number, number];
}

/** Parsed STL mesh data (flat interleaved arrays) */
export interface STLMeshData {
  filename: string;
  /** Byte size of source file */
  fileSize: number;
  triangleCount: number;
  /** Flat array: [x0,y0,z0, x1,y1,z1, ...] length = triangleCount * 9 */
  vertices: Float32Array;
  /** Flat array: same layout as vertices, one normal per vertex */
  normals: Float32Array;
  boundingBox: BoundingBox;
  isCompressed: boolean;
  originalTriangleCount: number;
  originalFileSize: number;
  /** Preserved originals so re-compression always starts from source */
  originalVertices?: Float32Array;
  originalNormals?: Float32Array;
  /** 0–100, only set when isCompressed=true */
  compressionRatio?: number;
}

/** Options for the compress() call */
export interface CompressOptions {
  /**
   * Target quality percentage (10–100).
   * 100 = no change, 10 = most aggressive.
   */
  quality: number;
}

/** Result returned by compressSTLBlob */
export interface CompressResult {
  blob: Blob;
  originalTriangleCount: number;
  compressedTriangleCount: number;
  originalSize: number;
  compressedSize: number;
  compressionRatio: number;
}

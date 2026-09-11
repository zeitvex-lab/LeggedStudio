/**
 * STL Compressor - Public API
 *
 * Entry point for the stl-compressor core module.
 * All functions are pure and have no React/UI dependencies.
 */

export type { STLMeshData, BoundingBox, CompressOptions, CompressResult } from './types.ts';
export { parseSTL, serializeToBinarySTL } from './stlParser.ts';
export { compressMesh } from './meshCompressor.ts';
export {
  compressSTLBlobWithWorker,
  createStlCompressionWorkerClient,
  disposeStlCompressionWorker,
} from './stlCompressionWorkerBridge.ts';

import { compressSTLBlobInline } from './blobCompression.ts';
import type { CompressOptions, CompressResult } from './types.ts';

/**
 * High-level helper: take an STL Blob, compress it, and return a new Blob
 * together with compression statistics.
 *
 * Only STL files are processed; non-STL blobs (e.g. DAE, OBJ) are returned
 * unchanged with a compressionRatio of 0.
 *
 * @param blob     - Original mesh file as a Blob
 * @param filename - File name (used for format detection)
 * @param options  - Compression options (quality: 10–100)
 */
export async function compressSTLBlob(
  blob: Blob,
  filename: string,
  options: CompressOptions,
): Promise<CompressResult> {
  return await compressSTLBlobInline(blob, filename, options);
}

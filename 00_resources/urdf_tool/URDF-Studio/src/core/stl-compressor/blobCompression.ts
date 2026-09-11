import { compressMesh } from './meshCompressor.ts';
import { parseSTL, serializeToBinarySTL } from './stlParser.ts';
import type { CompressOptions, CompressResult } from './types.ts';

export function isSTLFilename(filename: string): boolean {
  return filename.split('.').pop()?.toLowerCase() === 'stl';
}

export function createPassthroughCompressResult(blob: Blob): CompressResult {
  return {
    blob,
    originalTriangleCount: 0,
    compressedTriangleCount: 0,
    originalSize: blob.size,
    compressedSize: blob.size,
    compressionRatio: 0,
  };
}

export async function compressSTLBlobInline(
  blob: Blob,
  filename: string,
  options: CompressOptions,
): Promise<CompressResult> {
  if (!isSTLFilename(filename)) {
    return createPassthroughCompressResult(blob);
  }

  const arrayBuffer = await blob.arrayBuffer();
  const meshData = parseSTL(arrayBuffer, filename);
  const compressed = compressMesh(meshData, options.quality);
  const outputBuffer = serializeToBinarySTL(compressed);
  const outputBlob = new Blob([outputBuffer], { type: 'application/octet-stream' });

  return {
    blob: outputBlob,
    originalTriangleCount: meshData.triangleCount,
    compressedTriangleCount: compressed.triangleCount,
    originalSize: blob.size,
    compressedSize: outputBlob.size,
    compressionRatio: compressed.compressionRatio ?? 0,
  };
}

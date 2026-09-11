import {
  createPassthroughCompressResult,
  compressSTLBlobInline,
  isSTLFilename,
} from './blobCompression.ts';
import type {
  SerializedStlCompressionResult,
  StlCompressionWorkerResponse,
} from './stlCompressionWorkerProtocol.ts';
import type { CompressOptions, CompressResult } from './types.ts';
import {
  createWorkerPoolClient,
  type WorkerLike,
} from '@/core/workers/workerPoolClient';

export interface CreateStlCompressionWorkerClientOptions {
  canUseWorker?: () => boolean;
  createWorker?: () => WorkerLike;
  fallbackToInline?: boolean;
}

export interface StlCompressionWorkerClient {
  compress: (
    blob: Blob,
    filename: string,
    options: CompressOptions,
  ) => Promise<CompressResult>;
  dispose: (rejectPendingWith?: unknown) => void;
}

const DEFAULT_STL_COMPRESSION_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

function hydrateCompressionResult(result: SerializedStlCompressionResult): CompressResult {
  const outputBlob = new Blob([result.outputBuffer], { type: 'application/octet-stream' });

  return {
    blob: outputBlob,
    originalTriangleCount: result.originalTriangleCount,
    compressedTriangleCount: result.compressedTriangleCount,
    originalSize: result.originalSize,
    compressedSize: result.compressedSize,
    compressionRatio: result.compressionRatio,
  };
}

export function createStlCompressionWorkerClient({
  canUseWorker = () => typeof Worker !== 'undefined',
  createWorker = () =>
    new Worker(new URL('./workers/stlCompression.worker.ts', import.meta.url), {
      type: 'module',
    }),
  fallbackToInline = true,
}: CreateStlCompressionWorkerClientOptions = {}): StlCompressionWorkerClient {
  const client = createWorkerPoolClient<
    StlCompressionWorkerResponse,
    SerializedStlCompressionResult
  >({
    label: 'STL compression',
    createWorker,
    canUseWorker,
    requestTimeoutMs: DEFAULT_STL_COMPRESSION_REQUEST_TIMEOUT_MS,
    getRequestId: (response) => response.requestId,
    isError: (response) => response.type === 'compress-stl-error',
    getError: (response) =>
      (response as { error?: string }).error || 'STL compression worker failed',
    getResult: (response) =>
      (response as { result: SerializedStlCompressionResult }).result,
  });

  const compress = async (
    blob: Blob,
    filename: string,
    options: CompressOptions,
  ): Promise<CompressResult> => {
    if (!isSTLFilename(filename)) {
      return createPassthroughCompressResult(blob);
    }

    if (!client.canUseWorker) {
      return await compressSTLBlobInline(blob, filename, options);
    }

    try {
      const sourceBuffer = await blob.arrayBuffer();
      const result = await client.dispatch(
        {
          type: 'compress-stl',
          filename,
          sourceBuffer,
          quality: options.quality,
        },
        [sourceBuffer],
      );

      return hydrateCompressionResult(result);
    } catch (error) {
      if (!fallbackToInline) {
        throw error;
      }

      return await compressSTLBlobInline(blob, filename, options);
    }
  };

  return {
    compress,
    dispose: (rejectPendingWith) => client.dispose(rejectPendingWith),
  };
}

const sharedStlCompressionWorkerClient = createStlCompressionWorkerClient();

export function compressSTLBlobWithWorker(
  blob: Blob,
  filename: string,
  options: CompressOptions,
): Promise<CompressResult> {
  return sharedStlCompressionWorkerClient.compress(blob, filename, options);
}

export function disposeStlCompressionWorker(rejectPendingWith?: unknown): void {
  sharedStlCompressionWorkerClient.dispose(rejectPendingWith);
}

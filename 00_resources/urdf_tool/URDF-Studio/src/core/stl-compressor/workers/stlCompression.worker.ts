/// <reference lib="webworker" />

import { compressMesh } from '../meshCompressor.ts';
import { parseSTL, serializeToBinarySTL } from '../stlParser.ts';
import type {
  StlCompressionWorkerRequest,
  StlCompressionWorkerResponse,
} from '../stlCompressionWorkerProtocol.ts';

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;

workerScope.addEventListener(
  'message',
  (event: MessageEvent<StlCompressionWorkerRequest>) => {
    const message = event.data;
    if (!message || message.type !== 'compress-stl') {
      return;
    }

    try {
      const meshData = parseSTL(message.sourceBuffer, message.filename);
      const compressed = compressMesh(meshData, message.quality);
      const outputBuffer = serializeToBinarySTL(compressed);

      const response: StlCompressionWorkerResponse = {
        type: 'compress-stl-result',
        requestId: message.requestId,
        result: {
          outputBuffer,
          originalTriangleCount: meshData.triangleCount,
          compressedTriangleCount: compressed.triangleCount,
          originalSize: message.sourceBuffer.byteLength,
          compressedSize: outputBuffer.byteLength,
          compressionRatio: compressed.compressionRatio ?? 0,
        },
      };

      workerScope.postMessage(response, [outputBuffer]);
    } catch (error) {
      const response: StlCompressionWorkerResponse = {
        type: 'compress-stl-error',
        requestId: message.requestId,
        error: error instanceof Error ? error.message : 'Failed to compress STL in worker',
      };

      workerScope.postMessage(response);
    }
  },
);

export {};

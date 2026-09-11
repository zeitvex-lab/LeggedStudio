export interface CompressStlWorkerRequest {
  type: 'compress-stl';
  requestId: number;
  filename: string;
  sourceBuffer: ArrayBuffer;
  quality: number;
}

export interface SerializedStlCompressionResult {
  outputBuffer: ArrayBuffer;
  originalTriangleCount: number;
  compressedTriangleCount: number;
  originalSize: number;
  compressedSize: number;
  compressionRatio: number;
}

export interface CompressStlWorkerSuccessResponse {
  type: 'compress-stl-result';
  requestId: number;
  result: SerializedStlCompressionResult;
}

export interface CompressStlWorkerErrorResponse {
  type: 'compress-stl-error';
  requestId: number;
  error: string;
}

export type StlCompressionWorkerRequest = CompressStlWorkerRequest;
export type StlCompressionWorkerResponse =
  | CompressStlWorkerSuccessResponse
  | CompressStlWorkerErrorResponse;

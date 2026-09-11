import type { UsdBinaryArchiveWorkerPayload } from './usdBinaryArchiveWorkerTransfer.ts';

export interface ConvertUsdArchiveFilesToBinaryWorkerRequest {
  type: 'convert-usd-archive-files-to-binary';
  requestId: number;
  archiveFiles: UsdBinaryArchiveWorkerPayload;
}

export interface ConvertUsdArchiveFilesToBinaryWorkerProgress {
  type: 'convert-usd-archive-files-to-binary-progress';
  requestId: number;
  current: number;
  total: number;
  filePath: string;
}

export interface ConvertUsdArchiveFilesToBinaryWorkerResult {
  type: 'convert-usd-archive-files-to-binary-result';
  requestId: number;
  result: UsdBinaryArchiveWorkerPayload;
}

export interface ConvertUsdArchiveFilesToBinaryWorkerError {
  type: 'convert-usd-archive-files-to-binary-error';
  requestId: number;
  error: string;
}

export type UsdBinaryArchiveWorkerRequest =
  ConvertUsdArchiveFilesToBinaryWorkerRequest;

export type UsdBinaryArchiveWorkerResponse =
  | ConvertUsdArchiveFilesToBinaryWorkerProgress
  | ConvertUsdArchiveFilesToBinaryWorkerResult
  | ConvertUsdArchiveFilesToBinaryWorkerError;

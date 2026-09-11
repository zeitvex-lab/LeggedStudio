import type { ExportRobotToUsdProgress } from './usdExportCoordinator.ts';
import type {
  UsdExportWorkerRequestPayload,
  UsdExportWorkerResultPayload,
} from './usdExportWorkerTransfer.ts';

export interface ExportRobotToUsdWorkerRequest {
  type: 'export-robot-to-usd';
  requestId: number;
  payload: UsdExportWorkerRequestPayload;
}

export interface ExportRobotToUsdWorkerProgressResponse {
  type: 'export-robot-to-usd-progress';
  requestId: number;
  progress: ExportRobotToUsdProgress;
}

export interface ExportRobotToUsdWorkerResultResponse {
  type: 'export-robot-to-usd-result';
  requestId: number;
  result: UsdExportWorkerResultPayload;
}

export interface ExportRobotToUsdWorkerErrorResponse {
  type: 'export-robot-to-usd-error';
  requestId: number;
  error?: string;
}

export type UsdExportWorkerRequest = ExportRobotToUsdWorkerRequest;
export type UsdExportWorkerResponse =
  | ExportRobotToUsdWorkerProgressResponse
  | ExportRobotToUsdWorkerResultResponse
  | ExportRobotToUsdWorkerErrorResponse;

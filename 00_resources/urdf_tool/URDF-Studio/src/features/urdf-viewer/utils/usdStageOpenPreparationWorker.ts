import type { RobotFile } from '@/types';
import type { UsdStageOpenPreparationWorkerContextSnapshot } from './usdStageOpenPreparationWorkerPayload.ts';
import type { PreparedUsdStageOpenWorkerPayload } from './usdStageOpenPreparationTransfer.ts';

type StageOpenSourceFile = Pick<RobotFile, 'name' | 'content' | 'blobUrl'>;
type StageOpenAvailableFile = Array<Pick<RobotFile, 'name' | 'content' | 'blobUrl' | 'format'>>;

export interface PrepareUsdStageOpenWorkerRequest {
  type: 'prepare-usd-stage-open';
  requestId: number;
  sourceFile: StageOpenSourceFile;
  availableFiles?: StageOpenAvailableFile;
  assets?: Record<string, string>;
  contextId?: string;
}

export interface SyncUsdStageOpenWorkerContextRequest {
  type: 'sync-context';
  contextId: string;
  context: UsdStageOpenPreparationWorkerContextSnapshot;
}

export interface PrepareUsdStageOpenWorkerResponse {
  type: 'prepare-usd-stage-open-result' | 'prepare-usd-stage-open-error';
  requestId: number;
  result?: PreparedUsdStageOpenWorkerPayload;
  error?: string;
}

export type UsdStageOpenPreparationWorkerRequest =
  | PrepareUsdStageOpenWorkerRequest
  | SyncUsdStageOpenWorkerContextRequest;
export type UsdStageOpenPreparationWorkerResponse = PrepareUsdStageOpenWorkerResponse;

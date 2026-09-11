import type {
  CollisionOptimizationAnalysis,
  CollisionOptimizationAsyncOptions,
  CollisionOptimizationSettings,
  CollisionOptimizationSource,
} from './collisionOptimization';

export type CollisionOptimizationWorkerStage =
  | 'prepare-base'
  | 'mesh-analysis'
  | 'clearance'
  | 'candidates'
  | 'finalizing';

export type CollisionOptimizationWorkerProgressStatus =
  | 'started'
  | 'progress'
  | 'completed';

export interface CollisionOptimizationWorkerProgress {
  requestId: number;
  stage: CollisionOptimizationWorkerStage;
  status: CollisionOptimizationWorkerProgressStatus;
  completed?: number;
  total?: number;
}

export type CollisionOptimizationWorkerProgressHandler = (
  progress: CollisionOptimizationWorkerProgress,
) => void;

export type CollisionOptimizationWorkerRequestOptions = Omit<
  CollisionOptimizationAsyncOptions,
  'signal'
>;

export interface CollisionOptimizationWorkerAnalyzeArgs {
  source: CollisionOptimizationSource;
  assets: Record<string, string>;
  settings: CollisionOptimizationSettings;
  options?: CollisionOptimizationWorkerRequestOptions;
  signal?: AbortSignal;
  onProgress?: CollisionOptimizationWorkerProgressHandler;
}

export interface CollisionOptimizationInlineAnalyzeArgs
  extends CollisionOptimizationWorkerAnalyzeArgs {
  requestId: number;
}

export type CollisionOptimizationWorkerRequest =
  | {
      type: 'analyze';
      requestId: number;
      source: CollisionOptimizationSource;
      assets: Record<string, string>;
      settings: CollisionOptimizationSettings;
      options?: CollisionOptimizationWorkerRequestOptions;
    }
  | {
      type: 'cancel';
      requestId: number;
    };

export type CollisionOptimizationWorkerResponse =
  | ({
      type: 'progress';
    } & CollisionOptimizationWorkerProgress)
  | {
      type: 'result';
      requestId: number;
      analysis: CollisionOptimizationAnalysis;
    }
  | {
      type: 'error';
      requestId: number;
      error: string;
      name?: string;
    };

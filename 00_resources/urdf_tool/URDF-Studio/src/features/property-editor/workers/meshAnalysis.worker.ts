/// <reference lib="webworker" />

import {
  computeMeshAnalysisFromAssets,
  type MeshAnalysis,
  type MeshAnalysisOptions,
} from '../utils/geometryConversion';

interface MeshAnalysisWorkerTask {
  targetId: string;
  cacheKey: string;
  meshPath: string;
  dimensions?: { x: number; y: number; z: number };
  sourceFilePath?: string;
}

interface MeshAnalysisWorkerRequest {
  type: 'analyze-batch';
  requestId: number;
  assets: Record<string, string>;
  tasks: MeshAnalysisWorkerTask[];
  options?: MeshAnalysisOptions;
}

interface MeshAnalysisWorkerResult {
  targetId: string;
  cacheKey: string;
  analysis: MeshAnalysis | null;
}

type MeshAnalysisWorkerResponse =
  | {
      type: 'batch-result';
      requestId: number;
      results: MeshAnalysisWorkerResult[];
    }
  | {
      type: 'batch-error';
      requestId: number;
      error: string;
    };

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;

workerScope.addEventListener('message', async (event: MessageEvent<MeshAnalysisWorkerRequest>) => {
  const message = event.data;
  if (!message || message.type !== 'analyze-batch') {
    return;
  }

  try {
    const localCache = new Map<string, MeshAnalysis | null>();
    const results: MeshAnalysisWorkerResult[] = [];

    for (const task of message.tasks) {
      let analysis: MeshAnalysis | null;

      if (localCache.has(task.cacheKey)) {
        analysis = localCache.get(task.cacheKey) ?? null;
      } else {
        analysis = await computeMeshAnalysisFromAssets(
          task.meshPath,
          message.assets,
          task.dimensions,
          message.options,
          task.sourceFilePath,
        );
        localCache.set(task.cacheKey, analysis ?? null);
      }

      results.push({
        targetId: task.targetId,
        cacheKey: task.cacheKey,
        analysis: analysis ?? null,
      });
    }

    const response: MeshAnalysisWorkerResponse = {
      type: 'batch-result',
      requestId: message.requestId,
      results,
    };
    workerScope.postMessage(response);
  } catch (error) {
    const response: MeshAnalysisWorkerResponse = {
      type: 'batch-error',
      requestId: message.requestId,
      error: error instanceof Error ? error.message : String(error),
    };
    workerScope.postMessage(response);
  }
});

export {};

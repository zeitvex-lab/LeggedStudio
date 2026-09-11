/// <reference lib="webworker" />

import { analyzeCollisionOptimizationInline } from '../utils/collisionOptimizationWorkerAnalysis';
import type { CollisionOptimizationWorkerRequest } from '../utils/collisionOptimizationWorkerTypes';

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;
const activeControllers = new Map<number, AbortController>();

function toErrorName(error: unknown): string | undefined {
  return error instanceof Error ? error.name : undefined;
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Collision optimization worker failed';
}

async function handleAnalyze(
  message: Extract<CollisionOptimizationWorkerRequest, { type: 'analyze' }>,
): Promise<void> {
  const controller = new AbortController();
  activeControllers.set(message.requestId, controller);

  try {
    const analysis = await analyzeCollisionOptimizationInline({
      requestId: message.requestId,
      source: message.source,
      assets: message.assets,
      settings: message.settings,
      options: message.options,
      signal: controller.signal,
      onProgress: (progress) => {
        workerScope.postMessage({
          type: 'progress',
          ...progress,
        });
      },
    });

    if (!controller.signal.aborted) {
      workerScope.postMessage({
        type: 'result',
        requestId: message.requestId,
        analysis,
      });
    }
  } catch (error) {
    workerScope.postMessage({
      type: 'error',
      requestId: message.requestId,
      error: toErrorMessage(error),
      name: toErrorName(error),
    });
  } finally {
    activeControllers.delete(message.requestId);
  }
}

workerScope.addEventListener('message', (event: MessageEvent<CollisionOptimizationWorkerRequest>) => {
  const message = event.data;
  if (!message) {
    return;
  }

  if (message.type === 'cancel') {
    activeControllers.get(message.requestId)?.abort();
    return;
  }

  if (message.type === 'analyze') {
    void handleAnalyze(message);
  }
});

export {};

import { exportRobotToUsd } from '../utils/usdExportCoordinator.ts';
import type { UsdExportWorkerRequest, UsdExportWorkerResponse } from '../utils/usdExportWorker.ts';
import {
  hydrateUsdExportRequestFromWorker,
  serializeUsdExportResultForWorker,
} from '../utils/usdExportWorkerTransfer.ts';

const workerScope = self as unknown as DedicatedWorkerGlobalScope;

function toWorkerErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

async function handleWorkerMessage(message: UsdExportWorkerRequest): Promise<void> {
  if (message.type !== 'export-robot-to-usd') {
    return;
  }

  try {
    const options = hydrateUsdExportRequestFromWorker(message.payload);
    const result = await exportRobotToUsd({
      ...options,
      onProgress: (progress) => {
        const response: UsdExportWorkerResponse = {
          type: 'export-robot-to-usd-progress',
          requestId: message.requestId,
          progress,
        };
        workerScope.postMessage(response);
      },
    });
    const serialized = await serializeUsdExportResultForWorker(result);
    const response: UsdExportWorkerResponse = {
      type: 'export-robot-to-usd-result',
      requestId: message.requestId,
      result: serialized.payload,
    };
    workerScope.postMessage(response, serialized.transferables);
  } catch (error) {
    const response: UsdExportWorkerResponse = {
      type: 'export-robot-to-usd-error',
      requestId: message.requestId,
      error: toWorkerErrorMessage(error),
    };
    workerScope.postMessage(response);
  }
}

workerScope.addEventListener('message', (event: MessageEvent<UsdExportWorkerRequest>) => {
  void handleWorkerMessage(event.data);
});

export {};

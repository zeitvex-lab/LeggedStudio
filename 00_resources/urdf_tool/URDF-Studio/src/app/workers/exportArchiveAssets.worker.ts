/// <reference lib="webworker" />

import {
  collectPreparedExportArchiveAssetTransferables,
  hydratePrepareExportArchiveAssetsArgsFromWorker,
  prepareExportArchiveAssets,
  type ExportArchiveAssetsWorkerRequest,
  type ExportArchiveAssetsWorkerResponse,
} from '../utils/exportArchiveAssetsWorker.ts';

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;

workerScope.addEventListener(
  'message',
  (event: MessageEvent<ExportArchiveAssetsWorkerRequest>) => {
    const message = event.data;
    if (!message) {
      return;
    }

    void (async () => {
      try {
        const result = await prepareExportArchiveAssets(
          hydratePrepareExportArchiveAssetsArgsFromWorker(message.payload, (progress) => {
            const progressResponse: ExportArchiveAssetsWorkerResponse = {
              type: 'prepare-export-archive-assets-progress',
              requestId: message.requestId,
              progress,
            };
            workerScope.postMessage(progressResponse);
          }),
        );
        const response: ExportArchiveAssetsWorkerResponse = {
          type: 'prepare-export-archive-assets-result',
          requestId: message.requestId,
          result,
        };
        workerScope.postMessage(response, collectPreparedExportArchiveAssetTransferables(result));
      } catch (error) {
        const response: ExportArchiveAssetsWorkerResponse = {
          type: 'prepare-export-archive-assets-error',
          requestId: message.requestId,
          error: error instanceof Error ? error.message : 'Export archive assets worker failed',
        };
        workerScope.postMessage(response);
      }
    })();
  },
);

export {};

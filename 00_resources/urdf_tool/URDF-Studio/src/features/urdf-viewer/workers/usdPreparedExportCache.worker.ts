/// <reference lib="webworker" />

import { prepareUsdExportCacheFromResolvedSnapshot } from '../utils/usdExportBundle.ts';
import { serializePreparedUsdExportCacheForWorker } from '../utils/usdPreparedExportCacheWorkerTransfer.ts';
import type {
  UsdPreparedExportCacheWorkerRequest,
  UsdPreparedExportCacheWorkerResponse,
} from '../utils/usdPreparedExportCacheWorker.ts';

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;

function formatWorkerError(error: unknown): string {
  if (!(error instanceof Error)) {
    return 'USD prepared export cache worker failed';
  }

  const causeMessage = error.cause instanceof Error ? ` Cause: ${error.cause.message}` : '';

  return `${error.message}${causeMessage}`;
}

workerScope.addEventListener(
  'message',
  (event: MessageEvent<UsdPreparedExportCacheWorkerRequest>) => {
    const message = event.data;
    if (!message) {
      return;
    }

    void (async () => {
      try {
        const result = prepareUsdExportCacheFromResolvedSnapshot(
          message.snapshot,
          message.resolution,
          { includeTransferBytes: true },
        );
        const serialized = await serializePreparedUsdExportCacheForWorker(result);
        const response: UsdPreparedExportCacheWorkerResponse = {
          type: 'prepare-usd-prepared-export-cache-result',
          requestId: message.requestId,
          result: serialized.payload,
        };
        workerScope.postMessage(response, serialized.transferables);
      } catch (error) {
        const response: UsdPreparedExportCacheWorkerResponse = {
          type: 'prepare-usd-prepared-export-cache-error',
          requestId: message.requestId,
          error: formatWorkerError(error),
        };
        workerScope.postMessage(response);
      }
    })();
  },
);

export {};

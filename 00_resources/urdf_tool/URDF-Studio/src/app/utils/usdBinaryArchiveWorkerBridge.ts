import type {
  ConvertUsdArchiveFilesToBinaryWorkerRequest,
  UsdBinaryArchiveWorkerResponse,
} from './usdBinaryArchiveWorker.ts';
import {
  hydrateUsdBinaryArchiveFilesFromWorker,
  serializeUsdBinaryArchiveFilesForWorker,
} from './usdBinaryArchiveWorkerTransfer.ts';

interface WorkerLike {
  addEventListener: Worker['addEventListener'];
  removeEventListener: Worker['removeEventListener'];
  postMessage: Worker['postMessage'];
  terminate: Worker['terminate'];
}

interface PendingWorkerRequest {
  resolve: (value: Map<string, Blob>) => void;
  reject: (error: unknown) => void;
  onProgress?: (progress: {
    current: number;
    total: number;
    filePath: string;
  }) => void;
}

interface CreateUsdBinaryArchiveWorkerClientOptions {
  canUseWorker?: () => boolean;
  createWorker?: () => WorkerLike;
  /**
   * Per-request timeout in ms. If the worker goes silent, the pending request
   * is rejected so the UI never hangs forever.
   */
  requestTimeoutMs?: number;
}

interface ConvertUsdArchiveFilesToBinaryWithWorkerOptions {
  onProgress?: (progress: {
    current: number;
    total: number;
    filePath: string;
  }) => void;
}

interface UsdBinaryArchiveWorkerClient {
  dispose: (rejectPendingWith?: unknown) => void;
  convert: (
    archiveFiles: Map<string, Blob>,
    options?: ConvertUsdArchiveFilesToBinaryWithWorkerOptions,
  ) => Promise<Map<string, Blob>>;
}

// 5 minutes. USD crate conversion for large models (e.g. go2 with multi-MB
// DAE sublayers) can take a while, but never this long under healthy
// conditions. If we exceed it the worker is presumed dead (silent WASM trap)
// and we tear it down so the next export attempt can rebuild a fresh worker.
const DEFAULT_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

function createWorkerError(event: ErrorEvent | { error?: unknown; message?: string }): Error {
  if (event.error instanceof Error) {
    return event.error;
  }

  return new Error(event.message || 'USD binary archive worker failed');
}

export function createUsdBinaryArchiveWorkerClient(
  {
    canUseWorker = () => typeof Worker !== 'undefined',
    createWorker = () => new Worker(
      new URL('../workers/usdBinaryArchive.worker.ts', import.meta.url),
      { type: 'module' },
    ),
    requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  }: CreateUsdBinaryArchiveWorkerClientOptions = {},
): UsdBinaryArchiveWorkerClient {
  const pendingRequests = new Map<number, PendingWorkerRequest>();
  let requestIdCounter = 0;
  let sharedWorker: WorkerLike | null = null;
  let workerUnavailable = false;

  const clearPendingRequest = (requestId: number): PendingWorkerRequest | null => {
    const pendingRequest = pendingRequests.get(requestId) ?? null;
    if (!pendingRequest) {
      return null;
    }

    pendingRequests.delete(requestId);
    return pendingRequest;
  };

  const disposeSharedWorker = (rejectPendingWith?: unknown): void => {
    const rejectionReason = rejectPendingWith ?? new Error('USD binary archive worker disposed');

    if (sharedWorker) {
      sharedWorker.removeEventListener('message', handleSharedWorkerMessage as EventListener);
      sharedWorker.removeEventListener('error', handleSharedWorkerError as EventListener);
      sharedWorker.removeEventListener(
        'messageerror',
        handleSharedWorkerMessageError as EventListener,
      );
      sharedWorker.terminate();
      sharedWorker = null;
    }

    Array.from(pendingRequests.entries()).forEach(([requestId, request]) => {
      clearPendingRequest(requestId);
      request.reject(rejectionReason);
    });
  };

  const handleSharedWorkerMessage = (event: MessageEvent<UsdBinaryArchiveWorkerResponse>): void => {
    const message = event.data;
    if (!message) {
      return;
    }

    const pendingRequest = pendingRequests.get(message.requestId) ?? null;
    if (!pendingRequest) {
      return;
    }

    if (message.type === 'convert-usd-archive-files-to-binary-progress') {
      pendingRequest.onProgress?.({
        current: message.current,
        total: message.total,
        filePath: message.filePath,
      });
      return;
    }

    clearPendingRequest(message.requestId);

    if (message.type === 'convert-usd-archive-files-to-binary-error') {
      // The worker reports a conversion error. Because the worker side closes
      // itself after any conversion failure, we must tear it down here too.
      // Otherwise the next convert() would reuse a worker whose thread is
      // already gone and hang forever.
      const workerError = new Error(message.error || 'USD binary archive worker failed');
      pendingRequest.reject(workerError);
      disposeSharedWorker(workerError);
      return;
    }

    pendingRequest.resolve(hydrateUsdBinaryArchiveFilesFromWorker(message.result));
  };

  const handleSharedWorkerError = (event: ErrorEvent): void => {
    // Mark unavailable so the in-flight request can reject, and tear down the
    // dead worker. We do NOT treat this as permanent: ensureSharedWorker clears
    // the flag once sharedWorker is null again, so the next convert() builds a
    // fresh worker instead of failing forever.
    workerUnavailable = true;
    disposeSharedWorker(createWorkerError(event));
  };

  const handleSharedWorkerMessageError = (): void => {
    workerUnavailable = true;
    disposeSharedWorker(new Error('USD binary archive worker message transfer failed'));
  };

  const ensureSharedWorker = (): WorkerLike => {
    if (!sharedWorker) {
      // Previous worker was terminated (post-error or post-timeout). A fresh
      // worker means a fresh WASM runtime, so the previous unavailability no
      // longer applies.
      workerUnavailable = false;
      sharedWorker = createWorker();
      sharedWorker.addEventListener('message', handleSharedWorkerMessage as EventListener);
      sharedWorker.addEventListener('error', handleSharedWorkerError as EventListener);
      sharedWorker.addEventListener('messageerror', handleSharedWorkerMessageError as EventListener);
    }

    return sharedWorker;
  };

  const convert = async (
    archiveFiles: Map<string, Blob>,
    options: ConvertUsdArchiveFilesToBinaryWithWorkerOptions = {},
  ): Promise<Map<string, Blob>> => {
    if (!canUseWorker()) {
      throw new Error('Web Worker is not available in this environment');
    }

    // If a worker is mid-teardown (sharedWorker still set but flagged
    // unavailable), force disposal first so ensureSharedWorker can rebuild.
    if (workerUnavailable) {
      disposeSharedWorker(new Error('USD binary archive worker reset before retry'));
    }

    const serialized = await serializeUsdBinaryArchiveFilesForWorker(archiveFiles);

    return new Promise<Map<string, Blob>>((resolveRequest, rejectRequest) => {
      const requestId = ++requestIdCounter;
      let worker: WorkerLike;

      try {
        worker = ensureSharedWorker();
      } catch (error) {
        workerUnavailable = true;
        rejectRequest(error);
        return;
      }

      // Watchdog: if the worker neither resolves, rejects, nor errors within
      // the timeout, reject and tear down so the caller is not pinned forever.
      let timeoutId: ReturnType<typeof setTimeout> | undefined;
      const cancelTimeout = (): void => {
        if (timeoutId !== undefined) {
          clearTimeout(timeoutId);
          timeoutId = undefined;
        }
      };
      const wrappedResolve = (value: Map<string, Blob>): void => {
        cancelTimeout();
        resolveRequest(value);
      };
      const wrappedReject = (error: unknown): void => {
        cancelTimeout();
        rejectRequest(error);
      };
      const registerTimeout = (): void => {
        if (!requestTimeoutMs || !Number.isFinite(requestTimeoutMs) || requestTimeoutMs <= 0) {
          return;
        }
        timeoutId = setTimeout(() => {
          const timeoutError = new Error(
            'USD binary archive worker did not respond within the timeout '
              + `(likely a WASM crash). Request id: ${requestId}.`,
          );
          const stillPending = clearPendingRequest(requestId);
          if (!stillPending) return;
          disposeSharedWorker(timeoutError);
          stillPending.reject(timeoutError);
        }, requestTimeoutMs);
      };

      const request: ConvertUsdArchiveFilesToBinaryWorkerRequest = {
        type: 'convert-usd-archive-files-to-binary',
        requestId,
        archiveFiles: serialized.payload,
      };

      pendingRequests.set(requestId, {
        resolve: wrappedResolve,
        reject: wrappedReject,
        onProgress: options.onProgress,
      });
      registerTimeout();

      try {
        worker.postMessage(request, serialized.transferables);
      } catch (error) {
        cancelTimeout();
        clearPendingRequest(requestId);
        disposeSharedWorker(error);
        rejectRequest(error);
      }
    });
  };

  return {
    dispose: disposeSharedWorker,
    convert,
  };
}

const sharedUsdBinaryArchiveWorkerClient = createUsdBinaryArchiveWorkerClient();

export function convertUsdArchiveFilesToBinaryWithWorker(
  archiveFiles: Map<string, Blob>,
  options: ConvertUsdArchiveFilesToBinaryWithWorkerOptions = {},
): Promise<Map<string, Blob>> {
  return sharedUsdBinaryArchiveWorkerClient.convert(archiveFiles, options);
}

export function disposeUsdBinaryArchiveWorker(rejectPendingWith?: unknown): void {
  sharedUsdBinaryArchiveWorkerClient.dispose(rejectPendingWith);
}

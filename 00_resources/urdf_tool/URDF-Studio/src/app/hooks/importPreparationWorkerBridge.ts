import {
  type PrepareImportPayloadArgs,
  type ImportPreparationFileDescriptor,
  type PreparedDeferredImportAssetFile,
  type PreparedImportBlobFile,
  type PreparedImportPayload,
  type PrepareImportProgress,
  type ImportPreparationWorkerRequest,
  type ImportPreparationWorkerResponse,
} from '@/app/utils/importPreparation';

interface PendingWorkerRequest {
  resolve: (value: unknown) => void;
  reject: (error: unknown) => void;
  onProgress?: (progress: PrepareImportProgress) => void;
  timeoutId?: ReturnType<typeof setTimeout>;
}

const REQUEST_TIMEOUT_MS = 5 * 60 * 1000;
const pendingWorkerRequests = new Map<number, PendingWorkerRequest>();
let requestIdCounter = 0;
let sharedWorker: Worker | null = null;
let workerUnavailable = false;

function clearPendingWorkerRequest(requestId: number): PendingWorkerRequest | null {
  const pendingRequest = pendingWorkerRequests.get(requestId) ?? null;
  if (!pendingRequest) {
    return null;
  }

  pendingWorkerRequests.delete(requestId);
  if (pendingRequest.timeoutId !== undefined) {
    clearTimeout(pendingRequest.timeoutId);
    pendingRequest.timeoutId = undefined;
  }
  return pendingRequest;
}

function disposeSharedWorker(rejectPendingWith?: unknown): void {
  const rejectionReason = rejectPendingWith ?? new Error('Import preparation worker disposed');

  if (sharedWorker) {
    sharedWorker.removeEventListener('message', handleSharedWorkerMessage);
    sharedWorker.removeEventListener('error', handleSharedWorkerError);
    sharedWorker.removeEventListener('messageerror', handleSharedWorkerMessageError);
    sharedWorker.terminate();
    sharedWorker = null;
  }

  if (pendingWorkerRequests.size > 0) {
    Array.from(pendingWorkerRequests.entries()).forEach(([requestId, request]) => {
      clearPendingWorkerRequest(requestId);
      request.reject(rejectionReason);
    });
  }
}

function createWorkerTimeoutError(requestId: number): Error {
  return new Error(
    'Import preparation worker did not respond within the timeout '
      + `(likely a worker crash). Request id: ${requestId}. Timeout: ${REQUEST_TIMEOUT_MS} ms.`,
  );
}

function registerRequestTimeout(requestId: number, request: PendingWorkerRequest): void {
  request.timeoutId = setTimeout(() => {
    disposeSharedWorker(createWorkerTimeoutError(requestId));
  }, REQUEST_TIMEOUT_MS);
}

function handleSharedWorkerMessage(event: MessageEvent<ImportPreparationWorkerResponse>): void {
  const message = event.data;
  if (!message) {
    return;
  }

  const pendingRequest = pendingWorkerRequests.get(message.requestId) ?? null;
  if (!pendingRequest) {
    return;
  }

  if (
    message.type === 'prepare-import-progress' ||
    message.type === 'hydrate-deferred-import-assets-progress'
  ) {
    if (message.progress) {
      pendingRequest.onProgress?.(message.progress);
    }
    return;
  }

  clearPendingWorkerRequest(message.requestId);

  if (
    message.type === 'prepare-import-error' ||
    message.type === 'hydrate-deferred-import-assets-error'
  ) {
    pendingRequest.reject(new Error(message.error || 'Import preparation worker failed'));
    return;
  }

  if (message.type === 'prepare-import-result') {
    if (!message.payload) {
      pendingRequest.reject(new Error('Import preparation worker returned no payload'));
      return;
    }

    pendingRequest.resolve(message.payload);
    return;
  }

  if (message.type === 'hydrate-deferred-import-assets-result') {
    pendingRequest.resolve(message.assetFiles ?? []);
    return;
  }

  pendingRequest.reject(new Error('Import preparation worker returned an unexpected response'));
}

function handleSharedWorkerError(event: ErrorEvent): void {
  workerUnavailable = true;
  const error = event.error ?? new Error(event.message || 'Import preparation worker failed');
  disposeSharedWorker(error);
}

function handleSharedWorkerMessageError(): void {
  workerUnavailable = true;
  disposeSharedWorker(new Error('Import preparation worker message transfer failed'));
}

function ensureSharedWorker(): Worker {
  if (!sharedWorker) {
    workerUnavailable = false;
    sharedWorker = new Worker(new URL('../workers/importPreparation.worker.ts', import.meta.url), {
      type: 'module',
    });
    sharedWorker.addEventListener('message', handleSharedWorkerMessage);
    sharedWorker.addEventListener('error', handleSharedWorkerError);
    sharedWorker.addEventListener('messageerror', handleSharedWorkerMessageError);
  }

  return sharedWorker;
}

export async function prepareImportPayloadWithWorker(
  args: PrepareImportPayloadArgs,
): Promise<PreparedImportPayload> {
  if (workerUnavailable && sharedWorker) {
    throw new Error('Import preparation worker is unavailable');
  }

  if (typeof Worker === 'undefined') {
    throw new Error('Web Worker is not available in this environment');
  }

  return new Promise<PreparedImportPayload>((resolve, reject) => {
    const requestId = ++requestIdCounter;
    let worker: Worker;

    try {
      worker = ensureSharedWorker();
    } catch (error) {
      workerUnavailable = true;
      reject(error);
      return;
    }

    const files: ImportPreparationFileDescriptor[] = [...args.files].map((input) => {
      if (input instanceof File) {
        return {
          file: input,
          relativePath: input.webkitRelativePath || input.name,
        };
      }

      return {
        file: input.file,
        relativePath: input.relativePath || input.file.webkitRelativePath || input.file.name,
      };
    });
    const request: ImportPreparationWorkerRequest = {
      type: 'prepare-import',
      requestId,
      files,
      existingPaths: [...args.existingPaths],
      preResolvePreferredImport: args.preResolvePreferredImport,
    };

    const pendingRequest: PendingWorkerRequest = {
      resolve: (value) => resolve(value as PreparedImportPayload),
      reject,
      onProgress: args.onProgress,
    };
    pendingWorkerRequests.set(requestId, pendingRequest);
    registerRequestTimeout(requestId, pendingRequest);

    try {
      worker.postMessage(request);
    } catch (error) {
      workerUnavailable = true;
      clearPendingWorkerRequest(requestId);
      disposeSharedWorker(error);
      reject(error);
    }
  });
}

interface HydrateDeferredImportAssetsWithWorkerArgs {
  archiveFile: File;
  assetFiles: readonly PreparedDeferredImportAssetFile[];
  onProgress?: (progress: PrepareImportProgress) => void;
}

export async function hydrateDeferredImportAssetsWithWorker({
  archiveFile,
  assetFiles,
  onProgress,
}: HydrateDeferredImportAssetsWithWorkerArgs): Promise<PreparedImportBlobFile[]> {
  if (workerUnavailable && sharedWorker) {
    throw new Error('Import preparation worker is unavailable');
  }

  if (typeof Worker === 'undefined') {
    throw new Error('Web Worker is not available in this environment');
  }

  return new Promise<PreparedImportBlobFile[]>((resolve, reject) => {
    const requestId = ++requestIdCounter;
    let worker: Worker;

    try {
      worker = ensureSharedWorker();
    } catch (error) {
      workerUnavailable = true;
      reject(error);
      return;
    }

    const request: ImportPreparationWorkerRequest = {
      type: 'hydrate-deferred-import-assets',
      requestId,
      archiveFile,
      assetFiles: [...assetFiles],
    };

    const pendingRequest: PendingWorkerRequest = {
      resolve: (value) => resolve(value as PreparedImportBlobFile[]),
      reject,
      onProgress,
    };
    pendingWorkerRequests.set(requestId, pendingRequest);
    registerRequestTimeout(requestId, pendingRequest);

    try {
      worker.postMessage(request);
    } catch (error) {
      workerUnavailable = true;
      clearPendingWorkerRequest(requestId);
      disposeSharedWorker(error);
      reject(error);
    }
  });
}

export function disposeImportPreparationWorker(): void {
  workerUnavailable = false;
  requestIdCounter = 0;
  disposeSharedWorker();
}

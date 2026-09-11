import type { Language } from '@/shared/i18n';

import {
  hydrateImportedProjectResult,
  type ProjectImportResult,
} from './projectImport.ts';
import type {
  ImportProjectWorkerRequest,
  ProjectImportWorkerResponse,
} from './projectImportWorker.ts';

interface WorkerLike {
  addEventListener: Worker['addEventListener'];
  removeEventListener: Worker['removeEventListener'];
  postMessage: Worker['postMessage'];
  terminate: Worker['terminate'];
}

interface PendingWorkerRequest {
  resolve: (value: ProjectImportResult) => void;
  reject: (error: unknown) => void;
  timeoutId?: ReturnType<typeof setTimeout>;
}

interface CreateProjectImportWorkerClientOptions {
  canUseWorker?: () => boolean;
  createWorker?: () => WorkerLike;
  requestTimeoutMs?: number;
}

interface ProjectImportWorkerClient {
  dispose: (rejectPendingWith?: unknown) => void;
  import: (file: File, lang?: Language) => Promise<ProjectImportResult>;
}

function createWorkerError(event: ErrorEvent | { error?: unknown; message?: string }): Error {
  if (event.error instanceof Error) {
    return event.error;
  }

  return new Error(event.message || 'Project import worker failed');
}

const DEFAULT_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

function createWorkerTimeoutError(requestId: number, timeoutMs: number): Error {
  return new Error(
    'Project import worker did not respond within the timeout '
      + `(likely a worker crash). Request id: ${requestId}. Timeout: ${timeoutMs} ms.`,
  );
}

export function createProjectImportWorkerClient({
  canUseWorker = () => typeof Worker !== 'undefined',
  createWorker = () =>
    new Worker(new URL('../workers/projectImport.worker.ts', import.meta.url), {
      type: 'module',
    }),
  requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
}: CreateProjectImportWorkerClientOptions = {}): ProjectImportWorkerClient {
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
    if (pendingRequest.timeoutId !== undefined) {
      clearTimeout(pendingRequest.timeoutId);
      pendingRequest.timeoutId = undefined;
    }
    return pendingRequest;
  };

  const disposeSharedWorker = (rejectPendingWith?: unknown): void => {
    const rejectionReason = rejectPendingWith ?? new Error('Project import worker disposed');

    if (sharedWorker) {
      sharedWorker.removeEventListener('message', handleSharedWorkerMessage as EventListener);
      sharedWorker.removeEventListener('error', handleSharedWorkerError as EventListener);
      sharedWorker.removeEventListener('messageerror', handleSharedWorkerMessageError as EventListener);
      sharedWorker.terminate();
      sharedWorker = null;
    }

    if (pendingRequests.size > 0) {
      Array.from(pendingRequests.entries()).forEach(([requestId, request]) => {
        clearPendingRequest(requestId);
        request.reject(rejectionReason);
      });
    }
  };

  const registerRequestTimeout = (requestId: number, request: PendingWorkerRequest): void => {
    if (!requestTimeoutMs || !Number.isFinite(requestTimeoutMs) || requestTimeoutMs <= 0) {
      return;
    }

    request.timeoutId = setTimeout(() => {
      disposeSharedWorker(createWorkerTimeoutError(requestId, requestTimeoutMs));
    }, requestTimeoutMs);
  };

  const handleSharedWorkerMessage = (event: MessageEvent<ProjectImportWorkerResponse>): void => {
    const message = event.data;
    if (!message) {
      return;
    }

    const pendingRequest = clearPendingRequest(message.requestId);
    if (!pendingRequest) {
      return;
    }

    if (message.type === 'import-project-error') {
      pendingRequest.reject(new Error(message.error || 'Project import worker failed'));
      return;
    }

    try {
      pendingRequest.resolve(hydrateImportedProjectResult(message.result));
    } catch (error) {
      pendingRequest.reject(error);
    }
  };

  const handleSharedWorkerError = (event: ErrorEvent): void => {
    workerUnavailable = true;
    disposeSharedWorker(createWorkerError(event));
  };

  const handleSharedWorkerMessageError = (): void => {
    workerUnavailable = true;
    disposeSharedWorker(new Error('Project import worker message transfer failed'));
  };

  const ensureSharedWorker = (): WorkerLike => {
    if (!sharedWorker) {
      workerUnavailable = false;
      sharedWorker = createWorker();
      sharedWorker.addEventListener('message', handleSharedWorkerMessage as EventListener);
      sharedWorker.addEventListener('error', handleSharedWorkerError as EventListener);
      sharedWorker.addEventListener('messageerror', handleSharedWorkerMessageError as EventListener);
    }

    return sharedWorker;
  };

  const importProjectArchive = async (
    file: File,
    lang: Language = 'en',
  ): Promise<ProjectImportResult> => {
    if (workerUnavailable && sharedWorker) {
      throw new Error('Project import worker is unavailable');
    }

    if (!canUseWorker()) {
      throw new Error('Web Worker is not available in this environment');
    }

    return new Promise<ProjectImportResult>((resolveRequest, rejectRequest) => {
      const requestId = ++requestIdCounter;
      let worker: WorkerLike;

      try {
        worker = ensureSharedWorker();
      } catch (error) {
        workerUnavailable = true;
        rejectRequest(error);
        return;
      }

      const request: ImportProjectWorkerRequest = {
        type: 'import-project',
        requestId,
        file,
        lang,
      };

      const pendingRequest: PendingWorkerRequest = {
        resolve: resolveRequest,
        reject: rejectRequest,
      };
      pendingRequests.set(requestId, pendingRequest);
      registerRequestTimeout(requestId, pendingRequest);

      try {
        worker.postMessage(request);
      } catch (error) {
        workerUnavailable = true;
        clearPendingRequest(requestId);
        disposeSharedWorker(error);
        rejectRequest(error);
      }
    });
  };

  return {
    dispose: disposeSharedWorker,
    import: importProjectArchive,
  };
}

const sharedProjectImportWorkerClient = createProjectImportWorkerClient();

export function importProjectWithWorker(
  file: File,
  lang: Language = 'en',
): Promise<ProjectImportResult> {
  return sharedProjectImportWorkerClient.import(file, lang);
}

export function disposeProjectImportWorker(rejectPendingWith?: unknown): void {
  sharedProjectImportWorkerClient.dispose(rejectPendingWith);
}

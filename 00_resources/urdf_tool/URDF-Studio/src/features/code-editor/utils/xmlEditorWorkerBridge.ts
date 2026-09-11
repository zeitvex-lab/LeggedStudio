import type { SourceCodeDocumentFlavor, XmlCompletionEntry } from '../types';
import type { ValidationError } from './urdfValidation.ts';
import type { XmlDocumentValidationTexts } from './xmlDocumentValidation.ts';
import type {
  XmlEditorWorkerRequest,
  XmlEditorWorkerResponse,
} from './xmlEditorWorkerProtocol.ts';

interface PendingWorkerRequest<T> {
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
  timeoutId?: ReturnType<typeof setTimeout>;
}

const pendingWorkerRequests = new Map<number, PendingWorkerRequest<unknown>>();
const DEFAULT_XML_EDITOR_WORKER_REQUEST_TIMEOUT_MS = 30 * 1000;

let requestIdCounter = 0;
let sharedWorker: Worker | null = null;
let workerUnavailable = false;

const nextRequestId = (): number => {
  requestIdCounter += 1;
  return requestIdCounter;
};

const clearPendingRequest = (requestId: number): PendingWorkerRequest<unknown> | null => {
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
};

const rejectAllPendingRequests = (error: unknown): void => {
  Array.from(pendingWorkerRequests.entries()).forEach(([requestId, pendingRequest]) => {
    clearPendingRequest(requestId);
    pendingRequest.reject(error);
  });
};

const disposeSharedWorker = (rejectPendingWith?: unknown): void => {
  const rejectionReason = rejectPendingWith ?? new Error('XML editor worker disposed');

  if (sharedWorker) {
    sharedWorker.removeEventListener('message', handleSharedWorkerMessage);
    sharedWorker.removeEventListener('error', handleSharedWorkerError);
    sharedWorker.removeEventListener('messageerror', handleSharedWorkerMessageError);
    sharedWorker.terminate();
    sharedWorker = null;
  }

  rejectAllPendingRequests(rejectionReason);
};

const ensureSharedWorker = (): Worker => {
  if (!sharedWorker) {
    sharedWorker = new Worker(
      new URL('../workers/xmlEditor.worker.ts', import.meta.url),
      { type: 'module' },
    );
    sharedWorker.addEventListener('message', handleSharedWorkerMessage);
    sharedWorker.addEventListener('error', handleSharedWorkerError);
    sharedWorker.addEventListener('messageerror', handleSharedWorkerMessageError);
    workerUnavailable = false;
  }

  return sharedWorker;
};

const createWorkerTimeoutError = (requestId: number): Error =>
  new Error(
    `XML editor worker did not respond within ${DEFAULT_XML_EDITOR_WORKER_REQUEST_TIMEOUT_MS} ms. Request id: ${requestId}.`,
  );

const registerRequestTimeout = (
  requestId: number,
  pendingRequest: PendingWorkerRequest<unknown>,
): void => {
  pendingRequest.timeoutId = setTimeout(() => {
    workerUnavailable = true;
    disposeSharedWorker(createWorkerTimeoutError(requestId));
  }, DEFAULT_XML_EDITOR_WORKER_REQUEST_TIMEOUT_MS);
};

const handleSharedWorkerMessage = (event: MessageEvent<XmlEditorWorkerResponse>): void => {
  const response = event.data;
  if (!response) {
    return;
  }

  const pendingRequest = clearPendingRequest(response.requestId);
  if (!pendingRequest) {
    return;
  }

  if (response.type === 'xml-worker-error') {
    pendingRequest.reject(new Error(response.error || 'XML editor worker failed'));
    return;
  }

  if (response.type === 'xml-completion-result') {
    pendingRequest.resolve(response.entries);
    return;
  }

  if (response.type === 'xml-validation-result') {
    pendingRequest.resolve(response.errors);
    return;
  }

  pendingRequest.reject(new Error('Unexpected XML editor worker response'));
};

const handleSharedWorkerError = (event: ErrorEvent): void => {
  workerUnavailable = true;
  const error = event.error ?? new Error(event.message || 'XML editor worker failed');
  disposeSharedWorker(error);
};

const handleSharedWorkerMessageError = (): void => {
  workerUnavailable = true;
  disposeSharedWorker(new Error('XML editor worker message transfer failed'));
};

const postRequestToWorker = <TResponse>(request: XmlEditorWorkerRequest): Promise<TResponse> => {
  if (workerUnavailable && sharedWorker) {
    return Promise.reject(new Error('XML editor worker is unavailable'));
  }

  if (typeof Worker === 'undefined') {
    return Promise.reject(new Error('Web Worker is not available in this environment'));
  }

  return new Promise<TResponse>((resolve, reject) => {
    let worker: Worker;

    try {
      worker = ensureSharedWorker();
    } catch (error) {
      workerUnavailable = true;
      reject(error);
      return;
    }

    const pendingRequest: PendingWorkerRequest<unknown> = {
      resolve: (value: unknown) => resolve(value as TResponse),
      reject,
    };
    pendingWorkerRequests.set(request.requestId, pendingRequest);
    registerRequestTimeout(request.requestId, pendingRequest);

    try {
      worker.postMessage(request);
    } catch (error) {
      workerUnavailable = true;
      clearPendingRequest(request.requestId);
      disposeSharedWorker(error);
      reject(error);
    }
  });
};

export const requestXmlCompletionsWithWorker = (
  documentFlavor: SourceCodeDocumentFlavor,
  textBeforeCursor: string,
): Promise<XmlCompletionEntry[]> => postRequestToWorker<XmlCompletionEntry[]>({
  type: 'xml-completion',
  requestId: nextRequestId(),
  documentFlavor,
  textBeforeCursor,
});

export const requestXmlValidationWithWorker = (
  code: string,
  documentFlavor: SourceCodeDocumentFlavor,
  texts: XmlDocumentValidationTexts,
): Promise<ValidationError[]> => postRequestToWorker<ValidationError[]>({
  type: 'xml-validation',
  requestId: nextRequestId(),
  documentFlavor,
  code,
  texts,
});

export const disposeXmlEditorWorker = (): void => {
  workerUnavailable = false;
  disposeSharedWorker();
};

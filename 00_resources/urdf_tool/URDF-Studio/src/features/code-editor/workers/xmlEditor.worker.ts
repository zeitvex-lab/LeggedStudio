/// <reference lib="webworker" />

import { ensureWorkerXmlDomApis } from '@/core/utils/ensureWorkerXmlDomApis.ts';
import { getXmlCompletionEntries } from '../utils/xmlLanguageSupport.ts';
import { validateXmlDocumentByFlavor } from '../utils/xmlDocumentValidation.ts';
import type {
  XmlEditorWorkerRequest,
  XmlEditorWorkerResponse,
} from '../utils/xmlEditorWorkerProtocol.ts';

const workerScope = globalThis as unknown as DedicatedWorkerGlobalScope;
ensureWorkerXmlDomApis(workerScope as unknown as typeof globalThis);

workerScope.addEventListener('message', (event: MessageEvent<XmlEditorWorkerRequest>) => {
  const message = event.data;
  if (!message) {
    return;
  }
  const requestId = message.requestId;

  try {
    if (message.type === 'xml-completion') {
      const response: XmlEditorWorkerResponse = {
        type: 'xml-completion-result',
        requestId: message.requestId,
        entries: getXmlCompletionEntries(message.documentFlavor, message.textBeforeCursor),
      };
      workerScope.postMessage(response);
      return;
    }

    if (message.type === 'xml-validation') {
      const response: XmlEditorWorkerResponse = {
        type: 'xml-validation-result',
        requestId: message.requestId,
        errors: validateXmlDocumentByFlavor(message.code, message.documentFlavor, message.texts),
      };
      workerScope.postMessage(response);
      return;
    }

    const response: XmlEditorWorkerResponse = {
      type: 'xml-worker-error',
      requestId,
      error: `Unsupported XML worker request type: ${(message as { type?: string }).type || 'unknown'}`,
    };
    workerScope.postMessage(response);
  } catch (error) {
    const response: XmlEditorWorkerResponse = {
      type: 'xml-worker-error',
      requestId,
      error: error instanceof Error ? error.message : 'XML worker failed',
    };
    workerScope.postMessage(response);
  }
});

export {};

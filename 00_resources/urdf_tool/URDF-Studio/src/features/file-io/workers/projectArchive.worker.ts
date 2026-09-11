/// <reference lib="webworker" />

import {
  hydrateProjectArchiveEntriesFromWorker,
  type ProjectArchiveWorkerResultPayload,
} from '../utils/projectArchiveWorkerTransfer.ts';
import { buildProjectArchiveBlob } from '../utils/projectArchiveZip.ts';
import type {
  ProjectArchiveWorkerRequest,
  ProjectArchiveWorkerResponse,
} from '../utils/projectArchiveWorker.ts';

const workerScope = self as unknown as DedicatedWorkerGlobalScope;

function toWorkerErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return String(error);
}

async function handleWorkerMessage(message: ProjectArchiveWorkerRequest): Promise<void> {
  if (message.type !== 'build-project-archive') {
    return;
  }

  try {
    const archiveEntries = hydrateProjectArchiveEntriesFromWorker(message.payload);
    const blob = await buildProjectArchiveBlob(archiveEntries, {
      compressionLevel: message.compressionLevel,
      onProgress: ({ completed, total, label }) => {
        const response: ProjectArchiveWorkerResponse = {
          type: 'build-project-archive-progress',
          requestId: message.requestId,
          completed,
          total,
          label,
        };
        workerScope.postMessage(response);
      },
    });
    const resultBytes = await blob.arrayBuffer();
    const response: ProjectArchiveWorkerResponse = {
      type: 'build-project-archive-result',
      requestId: message.requestId,
      result: {
        bytes: resultBytes,
        mimeType: blob.type || 'application/zip',
      } satisfies ProjectArchiveWorkerResultPayload,
    };
    workerScope.postMessage(response, [resultBytes]);
  } catch (error) {
    const response: ProjectArchiveWorkerResponse = {
      type: 'build-project-archive-error',
      requestId: message.requestId,
      error: toWorkerErrorMessage(error),
    };
    workerScope.postMessage(response);
  }
}

workerScope.addEventListener('message', (event: MessageEvent<ProjectArchiveWorkerRequest>) => {
  void handleWorkerMessage(event.data);
});

export {};

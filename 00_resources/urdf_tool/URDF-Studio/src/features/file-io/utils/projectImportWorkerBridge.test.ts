import test from 'node:test';
import assert from 'node:assert/strict';

import { createDefaultWorkspace } from '@/core/robot';
import {
  PROJECT_ALL_FILE_CONTENTS_FILE,
  PROJECT_ASSET_MANIFEST_FILE,
  PROJECT_MOTOR_LIBRARY_FILE,
  PROJECT_WORKSPACE_HISTORY_FILE,
  PROJECT_WORKSPACE_STATE_FILE,
} from './projectArchive.ts';
import type { ProjectImportWorkerResponse } from './projectImportWorker.ts';
import { createProjectImportWorkerClient } from './projectImportWorkerBridge.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: unknown[] = [];

  public terminated = false;

  addEventListener(type: string, handler: WorkerEventHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerEventHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown, _transfer?: Transferable[]): void {
    this.postedMessages.push(message);
  }

  terminate(): void {
    this.terminated = true;
  }

  emitMessage(message: ProjectImportWorkerResponse): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data: message });
    });
  }

  emitMessageError(error: Error): void {
    this.listeners.get('messageerror')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }
}

test('project import worker client hydrates blob-backed library files on successful responses', async () => {
  const fakeWorker = new FakeWorker();
  const client = createProjectImportWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
  });

  const projectFile = new File(['project-archive'], 'demo.usp', {
    type: 'application/octet-stream',
  });
  const resultPromise = client.import(projectFile, 'en');

  for (let attempt = 0; attempt < 10 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  assert.equal(fakeWorker.postedMessages.length, 1);
  const postedRequest = fakeWorker.postedMessages[0] as { requestId: number; file: File };
  assert.equal(postedRequest.file.name, 'demo.usp');

  fakeWorker.emitMessage({
    type: 'import-project-result',
    requestId: postedRequest.requestId,
    result: {
      manifest: {
        version: '3.0',
        metadata: {
          name: 'demo_project',
          lastModified: '2026-04-05T00:00:00.000Z',
        },
        entries: {
          workspace: PROJECT_WORKSPACE_STATE_FILE,
          workspaceHistory: PROJECT_WORKSPACE_HISTORY_FILE,
          assets: PROJECT_ASSET_MANIFEST_FILE,
          allFileContents: PROJECT_ALL_FILE_CONTENTS_FILE,
          motorLibrary: PROJECT_MOTOR_LIBRARY_FILE,
        },
      },
      workspace: createDefaultWorkspace('demo_project'),
      workspaceHistory: {
        past: [],
        future: [],
        activity: [],
      },
      componentSourceDrafts: {},
      assets: {
        assetFiles: [
          {
            name: 'robots/demo.usd',
            blob: new Blob(['USD-BYTES'], { type: 'application/octet-stream' }),
          },
        ],
        availableFiles: [
          {
            name: 'robots/demo.usd',
            format: 'usd',
            content: '',
            blobPath: 'robots/demo.usd',
          },
        ],
        allFileContents: {},
        motorLibrary: {},
        selectedFileName: 'robots/demo.usd',
      },
      derivedCaches: { usdPreparedExportCaches: {} },
      warnings: [],
    },
  });

  const result = await resultPromise;
  assert.match(result.assets.assetUrls['robots/demo.usd'] ?? '', /^blob:/);
  assert.match(result.assets.availableFiles[0]?.blobUrl ?? '', /^blob:/);
});

test('project import worker client rejects immediately when Worker is unavailable', async () => {
  const originalWorker = globalThis.Worker;

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: undefined,
  });

  try {
    const client = createProjectImportWorkerClient();
    await assert.rejects(
      client.import(new File(['project'], 'demo.usp'), 'en'),
      /Web Worker is not available in this environment/i,
    );
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
  }
});

test('project import worker client rejects pending imports when message transfer fails', async () => {
  const fakeWorker = new FakeWorker();
  const client = createProjectImportWorkerClient({
    canUseWorker: () => true,
    createWorker: () => fakeWorker as unknown as Worker,
    requestTimeoutMs: 0,
  });

  const resultPromise = client.import(new File(['project'], 'demo.usp'), 'en');
  assert.equal(fakeWorker.postedMessages.length, 1);

  fakeWorker.emitMessageError(new Error('structured clone failed'));

  await assert.rejects(resultPromise, /message transfer failed/i);
  assert.equal(fakeWorker.terminated, true);
});

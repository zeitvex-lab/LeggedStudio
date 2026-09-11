import type {
  BuildProjectArchiveWorkerRequest,
  ProjectArchiveWorkerResponse,
} from './projectArchiveWorker.ts';
import {
  hydrateProjectArchiveBlobFromWorker,
  serializeProjectArchiveEntriesForWorker,
  type ProjectArchiveEntryData,
} from './projectArchiveWorkerTransfer.ts';
import {
  createWorkerPoolClient,
  type WorkerLike,
  type PendingRequest,
} from '@/core/workers/workerPoolClient';

interface CreateProjectArchiveWorkerClientOptions {
  canUseWorker?: () => boolean;
  createWorker?: () => WorkerLike;
}

interface BuildProjectArchiveWithWorkerOptions {
  compressionLevel?: number;
  onProgress?: (progress: { completed: number; total: number; label?: string }) => void;
}

interface ProjectArchiveWorkerClient {
  dispose: (rejectPendingWith?: unknown) => void;
  build: (
    entries: Map<string, ProjectArchiveEntryData>,
    options?: BuildProjectArchiveWithWorkerOptions,
  ) => Promise<Blob>;
}

type ProgressPayload = {
  completed: number;
  total: number;
  label?: string;
};

const DEFAULT_PROJECT_ARCHIVE_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

export function createProjectArchiveWorkerClient({
  canUseWorker = () => typeof Worker !== 'undefined',
  createWorker = () =>
    new Worker(new URL('../workers/projectArchive.worker.ts', import.meta.url), { type: 'module' }),
}: CreateProjectArchiveWorkerClientOptions = {}): ProjectArchiveWorkerClient {
  const client = createWorkerPoolClient<ProjectArchiveWorkerResponse, Blob, ProgressPayload>({
    label: 'Project archive',
    createWorker,
    canUseWorker,
    requestTimeoutMs: DEFAULT_PROJECT_ARCHIVE_REQUEST_TIMEOUT_MS,
    getRequestId: (response) => response.requestId,
    isError: (response) => response.type === 'build-project-archive-error',
    getError: (response) =>
      (response as { error?: string }).error || 'Project archive worker failed',
    getResult: (response) =>
      hydrateProjectArchiveBlobFromWorker((response as { result: unknown }).result as any),
    isProgress: (response) => response.type === 'build-project-archive-progress',
    handleProgress: (response, request) => {
      const msg = response as { completed: number; total: number; label?: string };
      request.onProgress?.({
        completed: msg.completed,
        total: msg.total,
        label: msg.label,
      });
    },
  });

  const build = async (
    entries: Map<string, ProjectArchiveEntryData>,
    options: BuildProjectArchiveWithWorkerOptions = {},
  ): Promise<Blob> => {
    const serialized = await serializeProjectArchiveEntriesForWorker(entries);

    const request: Omit<BuildProjectArchiveWorkerRequest, 'requestId'> = {
      type: 'build-project-archive',
      payload: serialized.payload,
      compressionLevel: options.compressionLevel,
    };

    try {
      return await client.dispatch(request, serialized.transferables, options.onProgress as any);
    } catch (error) {
      if (
        error instanceof Error &&
        /Project archive worker is not available in this environment/i.test(error.message)
      ) {
        throw new Error('Web Worker is not available in this environment', { cause: error });
      }

      throw error;
    }
  };

  return {
    dispose: (rejectPendingWith) => client.dispose(rejectPendingWith),
    build,
  };
}

const sharedProjectArchiveWorkerClient = createProjectArchiveWorkerClient();

export function buildProjectArchiveBlobWithWorker(
  entries: Map<string, ProjectArchiveEntryData>,
  options: BuildProjectArchiveWithWorkerOptions = {},
): Promise<Blob> {
  return sharedProjectArchiveWorkerClient.build(entries, options);
}

export function disposeProjectArchiveWorker(rejectPendingWith?: unknown): void {
  sharedProjectArchiveWorkerClient.dispose(rejectPendingWith);
}

import { type MeshAnalysis, type MeshAnalysisOptions } from './geometryConversion';

interface MeshAnalysisBatchTask {
  targetId: string;
  cacheKey: string;
  meshPath: string;
  dimensions?: { x: number; y: number; z: number };
  sourceFilePath?: string;
}

interface AnalyzeMeshBatchArgs {
  assets: Record<string, string>;
  tasks: MeshAnalysisBatchTask[];
  options?: MeshAnalysisOptions;
  signal?: AbortSignal;
}

interface MeshAnalysisWorkerResult {
  targetId: string;
  cacheKey: string;
  analysis: MeshAnalysis | null;
}

interface MeshAnalysisWorkerResponse {
  type: 'batch-result' | 'batch-error';
  requestId: number;
  results?: MeshAnalysisWorkerResult[];
  error?: string;
}

interface MeshAnalysisWorkerClientDependencies {
  canUseWorker?: () => boolean;
  createWorker?: () => Worker;
  getWorkerCount?: () => number;
  requestTimeoutMs?: number;
}

interface WorkerPoolEntry {
  worker: Worker;
  pendingCount: number;
}

interface PendingWorkerRequest {
  workerEntry: WorkerPoolEntry;
  results: Record<string, MeshAnalysis | null>;
  resolve: () => void;
  reject: (error: unknown) => void;
  abortHandler?: () => void;
  signal?: AbortSignal;
  timeoutId?: ReturnType<typeof setTimeout>;
}

const MAX_MESH_ANALYSIS_CACHE_SIZE = 256;
const MAX_MESH_ANALYSIS_WORKER_COUNT = 4;
const DEFAULT_MESH_ANALYSIS_REQUEST_TIMEOUT_MS = 2 * 60 * 1000;

function createOptionsCacheKey(options?: MeshAnalysisOptions): string {
  return JSON.stringify({
    includePrimitiveFits: options?.includePrimitiveFits ?? 'default',
    includeSurfacePoints: options?.includeSurfacePoints ?? 'default',
    pointCollectionLimit: options?.pointCollectionLimit ?? 'default',
    surfacePointLimit: options?.surfacePointLimit ?? 'default',
  });
}

function createRequestCacheKey(cacheKey: string, options?: MeshAnalysisOptions): string {
  return `${cacheKey}::${createOptionsCacheKey(options)}`;
}

function createAbortError(): DOMException {
  return new DOMException('Mesh analysis aborted', 'AbortError');
}

function createWorkerTimeoutError(requestId: number, timeoutMs: number): Error {
  return new Error(
    `Mesh analysis worker did not respond within ${timeoutMs} ms. Request id: ${requestId}.`,
  );
}

function resolveDefaultWorkerCount(): number {
  const hardwareConcurrency =
    typeof navigator !== 'undefined' ? Number(navigator.hardwareConcurrency || 2) : 2;
  const normalizedHardwareConcurrency =
    Number.isFinite(hardwareConcurrency) && hardwareConcurrency > 0 ? hardwareConcurrency : 2;

  return Math.max(
    1,
    Math.min(MAX_MESH_ANALYSIS_WORKER_COUNT, Math.ceil(normalizedHardwareConcurrency / 3)),
  );
}

function createTaskChunks(
  pendingTasks: MeshAnalysisBatchTask[],
  chunkCount: number,
): MeshAnalysisBatchTask[][] {
  if (pendingTasks.length === 0) {
    return [];
  }

  const boundedChunkCount = Math.max(1, Math.min(chunkCount, pendingTasks.length));
  const taskGroupsByCacheKey = new Map<string, MeshAnalysisBatchTask[]>();
  pendingTasks.forEach((task) => {
    const taskGroup = taskGroupsByCacheKey.get(task.cacheKey);
    if (taskGroup) {
      taskGroup.push(task);
      return;
    }

    taskGroupsByCacheKey.set(task.cacheKey, [task]);
  });

  const chunks = Array.from({ length: boundedChunkCount }, () => [] as MeshAnalysisBatchTask[]);
  const chunkLoads = Array.from({ length: boundedChunkCount }, () => 0);
  const taskGroups = Array.from(taskGroupsByCacheKey.values()).sort((left, right) => {
    if (right.length !== left.length) {
      return right.length - left.length;
    }

    return left[0]!.cacheKey.localeCompare(right[0]!.cacheKey);
  });

  taskGroups.forEach((group) => {
    let targetChunkIndex = 0;
    for (let index = 1; index < chunks.length; index += 1) {
      if (chunkLoads[index]! < chunkLoads[targetChunkIndex]!) {
        targetChunkIndex = index;
      }
    }

    chunks[targetChunkIndex]!.push(...group);
    chunkLoads[targetChunkIndex]! += group.length;
  });

  return chunks.filter((chunk) => chunk.length > 0);
}

export function createMeshAnalysisWorkerClient({
  canUseWorker = () => typeof Worker !== 'undefined',
  createWorker = () =>
    new Worker(new URL('../workers/meshAnalysis.worker.ts', import.meta.url), { type: 'module' }),
  getWorkerCount = resolveDefaultWorkerCount,
  requestTimeoutMs = DEFAULT_MESH_ANALYSIS_REQUEST_TIMEOUT_MS,
}: MeshAnalysisWorkerClientDependencies = {}) {
  const meshAnalysisCache = new Map<string, MeshAnalysis | null>();
  const pendingWorkerRequests = new Map<number, PendingWorkerRequest>();
  const workerPool: WorkerPoolEntry[] = [];
  let requestIdCounter = 0;
  let workerUnavailable = false;
  let maxWorkerCount: number | null = null;

  const setMeshAnalysisCacheEntry = (cacheKey: string, analysis: MeshAnalysis | null): void => {
    if (meshAnalysisCache.has(cacheKey)) {
      meshAnalysisCache.delete(cacheKey);
    }

    meshAnalysisCache.set(cacheKey, analysis);

    while (meshAnalysisCache.size > MAX_MESH_ANALYSIS_CACHE_SIZE) {
      const oldestKey = meshAnalysisCache.keys().next().value;
      if (oldestKey === undefined) {
        break;
      }

      meshAnalysisCache.delete(oldestKey);
    }
  };

  const clearPendingWorkerRequest = (requestId: number): PendingWorkerRequest | null => {
    const pendingRequest = pendingWorkerRequests.get(requestId) ?? null;
    if (!pendingRequest) {
      return null;
    }

    pendingWorkerRequests.delete(requestId);
    if (pendingRequest.timeoutId !== undefined) {
      clearTimeout(pendingRequest.timeoutId);
      pendingRequest.timeoutId = undefined;
    }
    pendingRequest.workerEntry.pendingCount = Math.max(
      0,
      pendingRequest.workerEntry.pendingCount - 1,
    );
    if (pendingRequest.abortHandler) {
      pendingRequest.signal?.removeEventListener('abort', pendingRequest.abortHandler);
    }

    return pendingRequest;
  };

  const handleSharedWorkerMessage = (event: MessageEvent<MeshAnalysisWorkerResponse>): void => {
    const message = event.data;
    if (!message) {
      return;
    }

    const pendingRequest = clearPendingWorkerRequest(message.requestId);
    if (!pendingRequest) {
      return;
    }

    if (message.type === 'batch-error') {
      pendingRequest.reject(new Error(message.error || 'Mesh analysis worker failed'));
      return;
    }

    const workerResults = message.results ?? [];
    workerResults.forEach((entry) => {
      setMeshAnalysisCacheEntry(entry.cacheKey, entry.analysis ?? null);
      pendingRequest.results[entry.targetId] = entry.analysis ?? null;
    });
    pendingRequest.resolve();
  };

  const detachWorkerEntry = (entry: WorkerPoolEntry): void => {
    entry.worker.removeEventListener('message', handleSharedWorkerMessage as EventListener);
    entry.worker.removeEventListener('error', handleSharedWorkerError as EventListener);
    entry.worker.removeEventListener(
      'messageerror',
      handleSharedWorkerMessageError as EventListener,
    );
    entry.worker.terminate();
    entry.pendingCount = 0;
    const entryIndex = workerPool.indexOf(entry);
    if (entryIndex >= 0) {
      workerPool.splice(entryIndex, 1);
    }
  };

  const disposeWorkerEntry = (
    entry: WorkerPoolEntry,
    rejectPendingWith = new Error('Mesh analysis worker disposed'),
  ): void => {
    detachWorkerEntry(entry);

    Array.from(pendingWorkerRequests.entries()).forEach(([requestId, request]) => {
      if (request.workerEntry !== entry) {
        return;
      }

      clearPendingWorkerRequest(requestId);
      request.reject(rejectPendingWith);
    });
  };

  const disposeWorkerPool = (rejectPendingWith?: unknown): void => {
    const rejectionReason = rejectPendingWith ?? new Error('Mesh analysis worker disposed');

    [...workerPool].forEach((entry) => {
      detachWorkerEntry(entry);
    });
    Array.from(pendingWorkerRequests.entries()).forEach(([requestId, request]) => {
      clearPendingWorkerRequest(requestId);
      request.reject(rejectionReason);
    });
  };

  const handleSharedWorkerError = (event: ErrorEvent): void => {
    workerUnavailable = true;
    const error = event.error ?? new Error(event.message || 'Mesh analysis worker failed');
    disposeWorkerPool(error);
  };

  const handleSharedWorkerMessageError = (): void => {
    workerUnavailable = true;
    disposeWorkerPool(new Error('Mesh analysis worker message transfer failed'));
  };

  const resolveMaxWorkerCount = (): number => {
    if (maxWorkerCount === null) {
      maxWorkerCount = Math.max(1, getWorkerCount());
    }
    return maxWorkerCount;
  };

  const createWorkerPoolEntry = (): WorkerPoolEntry => {
    const worker = createWorker();
    worker.addEventListener('message', handleSharedWorkerMessage as EventListener);
    worker.addEventListener('error', handleSharedWorkerError as EventListener);
    worker.addEventListener('messageerror', handleSharedWorkerMessageError as EventListener);
    const entry: WorkerPoolEntry = {
      worker,
      pendingCount: 0,
    };
    workerPool.push(entry);
    workerUnavailable = false;
    return entry;
  };

  const registerRequestTimeout = (
    requestId: number,
    pendingRequest: PendingWorkerRequest,
  ): void => {
    if (!requestTimeoutMs || !Number.isFinite(requestTimeoutMs) || requestTimeoutMs <= 0) {
      return;
    }

    pendingRequest.timeoutId = setTimeout(() => {
      const timeoutError = createWorkerTimeoutError(requestId, requestTimeoutMs);
      workerUnavailable = true;
      disposeWorkerPool(timeoutError);
    }, requestTimeoutMs);
  };

  const ensureWorkerPool = (minimumWorkerCount = 1): WorkerPoolEntry[] => {
    const targetWorkerCount = Math.max(1, Math.min(resolveMaxWorkerCount(), minimumWorkerCount));
    while (workerPool.length < targetWorkerCount) {
      createWorkerPoolEntry();
    }

    return workerPool;
  };

  const pickWorkerEntry = (): WorkerPoolEntry => {
    const pool = ensureWorkerPool();
    const bestEntry = pool.reduce(
      (best, candidate) => (candidate.pendingCount < best.pendingCount ? candidate : best),
      pool[0]!,
    );

    if (bestEntry.pendingCount > 0 && workerPool.length < resolveMaxWorkerCount()) {
      return createWorkerPoolEntry();
    }

    return bestEntry;
  };

  const dispatchChunkToWorker = async ({
    assets,
    options,
    results,
    signal,
    tasks,
  }: AnalyzeMeshBatchArgs & {
    results: Record<string, MeshAnalysis | null>;
    tasks: MeshAnalysisBatchTask[];
  }): Promise<void> => {
    if (tasks.length === 0) {
      return;
    }

    if (signal?.aborted) {
      throw createAbortError();
    }

    return await new Promise<void>((resolve, reject) => {
      let workerEntry: WorkerPoolEntry;

      try {
        workerEntry = pickWorkerEntry();
      } catch (error) {
        workerUnavailable = true;
        disposeWorkerPool(error);
        reject(error);
        return;
      }

      const requestId = ++requestIdCounter;
      workerEntry.pendingCount += 1;

      const handleAbort = () => {
        if (!pendingWorkerRequests.has(requestId)) {
          return;
        }
        disposeWorkerEntry(workerEntry, createAbortError());
      };

      const pendingRequest: PendingWorkerRequest = {
        workerEntry,
        results,
        resolve,
        reject,
        abortHandler: handleAbort,
        signal,
      };
      pendingWorkerRequests.set(requestId, pendingRequest);
      signal?.addEventListener('abort', handleAbort, { once: true });
      registerRequestTimeout(requestId, pendingRequest);

      try {
        workerEntry.worker.postMessage({
          type: 'analyze-batch',
          requestId,
          assets,
          tasks,
          options,
        });
      } catch (error) {
        workerUnavailable = true;
        clearPendingWorkerRequest(requestId);
        disposeWorkerPool(error);
        reject(error);
      }
    });
  };

  const analyzeBatch = async ({
    assets,
    tasks,
    options,
    signal,
  }: AnalyzeMeshBatchArgs): Promise<Record<string, MeshAnalysis | null>> => {
    if (workerUnavailable && workerPool.length > 0) {
      throw new Error('Mesh analysis worker is unavailable');
    }

    const results: Record<string, MeshAnalysis | null> = {};
    const pendingTasks: MeshAnalysisBatchTask[] = [];

    tasks.forEach((task) => {
      const requestCacheKey = createRequestCacheKey(task.cacheKey, options);
      if (meshAnalysisCache.has(requestCacheKey)) {
        results[task.targetId] = meshAnalysisCache.get(requestCacheKey) ?? null;
        return;
      }

      pendingTasks.push({
        ...task,
        cacheKey: requestCacheKey,
      });
    });

    if (pendingTasks.length === 0) {
      return results;
    }

    if (!canUseWorker()) {
      throw new Error('Web Worker is not available in this environment');
    }

    const taskChunks = createTaskChunks(
      pendingTasks,
      Math.min(resolveMaxWorkerCount(), pendingTasks.length),
    );

    await Promise.all(
      taskChunks.map((chunk) =>
        dispatchChunkToWorker({
          assets,
          options,
          results,
          signal,
          tasks: chunk,
        }),
      ),
    );

    return results;
  };

  return {
    analyzeBatch,
    clearCache: () => {
      meshAnalysisCache.clear();
    },
    dispose: (rejectPendingWith?: unknown) => {
      disposeWorkerPool(rejectPendingWith);
    },
    reset: () => {
      disposeWorkerPool();
      meshAnalysisCache.clear();
      pendingWorkerRequests.clear();
      requestIdCounter = 0;
      workerUnavailable = false;
      maxWorkerCount = null;
    },
  };
}

const sharedMeshAnalysisWorkerClient = createMeshAnalysisWorkerClient();

export async function analyzeMeshBatchWithWorker({
  assets,
  tasks,
  options,
  signal,
}: AnalyzeMeshBatchArgs): Promise<Record<string, MeshAnalysis | null>> {
  return sharedMeshAnalysisWorkerClient.analyzeBatch({
    assets,
    tasks,
    options,
    signal,
  });
}

export function __resetMeshAnalysisWorkerBridgeForTests(): void {
  sharedMeshAnalysisWorkerClient.reset();
}

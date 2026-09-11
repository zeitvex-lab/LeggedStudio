import type { ExportRobotToUsdOptions, ExportRobotToUsdPayload } from './usdExportCoordinator.ts';
import { assertUsdExportWorkerSupport } from './usdExportWorkerSupport.ts';
import type { ExportRobotToUsdWorkerRequest, UsdExportWorkerResponse } from './usdExportWorker.ts';
import {
  hydrateUsdExportResultFromWorker,
  serializeUsdExportRequestForWorker,
} from './usdExportWorkerTransfer.ts';
import {
  createWorkerPoolClient,
  type WorkerLike,
  type PendingRequest,
} from '@/core/workers/workerPoolClient';

interface CreateUsdExportWorkerClientOptions {
  canUseWorker?: () => boolean;
  createWorker?: () => WorkerLike;
}

interface UsdExportWorkerClient {
  dispose: (rejectPendingWith?: unknown) => void;
  export: (options: ExportRobotToUsdOptions) => Promise<ExportRobotToUsdPayload>;
}

const DEFAULT_USD_EXPORT_REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

export function createUsdExportWorkerClient({
  canUseWorker = () => typeof Worker !== 'undefined',
  createWorker = () =>
    new Worker(new URL('../workers/usdExport.worker.ts', import.meta.url), { type: 'module' }),
}: CreateUsdExportWorkerClientOptions = {}): UsdExportWorkerClient {
  const client = createWorkerPoolClient<
    UsdExportWorkerResponse,
    ExportRobotToUsdPayload,
    ExportRobotToUsdOptions['onProgress'] extends ((p: infer P) => void) | undefined ? P : never
  >({
    label: 'USD export',
    createWorker,
    canUseWorker,
    requestTimeoutMs: DEFAULT_USD_EXPORT_REQUEST_TIMEOUT_MS,
    getRequestId: (response) => response.requestId,
    isError: (response) => response.type === 'export-robot-to-usd-error',
    getError: (response) => (response as { error?: string }).error || 'USD export worker failed',
    getResult: (response) =>
      hydrateUsdExportResultFromWorker((response as { result: unknown }).result as any),
    isProgress: (response) => response.type === 'export-robot-to-usd-progress',
    handleProgress: (response, request) => {
      request.onProgress?.((response as { progress: unknown }).progress as any);
    },
  });

  const exportWithWorker = async (
    options: ExportRobotToUsdOptions,
  ): Promise<ExportRobotToUsdPayload> => {
    assertUsdExportWorkerSupport(options.robot);

    const { onProgress, ...requestOptions } = options;
    const serialized = await serializeUsdExportRequestForWorker(requestOptions);

    const request: Omit<ExportRobotToUsdWorkerRequest, 'requestId'> = {
      type: 'export-robot-to-usd',
      payload: serialized.payload,
    };

    return client.dispatch(request, serialized.transferables, onProgress as any);
  };

  return {
    dispose: (rejectPendingWith) => client.dispose(rejectPendingWith),
    export: exportWithWorker,
  };
}

const sharedUsdExportWorkerClient = createUsdExportWorkerClient();

export function exportRobotToUsdWithWorker(
  options: ExportRobotToUsdOptions,
): Promise<ExportRobotToUsdPayload> {
  return sharedUsdExportWorkerClient.export(options);
}

export function disposeUsdExportWorker(rejectPendingWith?: unknown): void {
  sharedUsdExportWorkerClient.dispose(rejectPendingWith);
}

import type { RobotState } from '@/types';

import type {
  ExportRobotToUsdOptions,
  ExportRobotToUsdPayload,
  UsdLayerFileFormat,
  UsdMeshCompressionOptions,
  UsdPackageLayoutProfile,
} from './usdExportCoordinator.ts';

export interface UsdExportWorkerTransferFile {
  path: string;
  blob: Blob;
}

export interface UsdExportWorkerRequestPayload {
  robot: RobotState;
  exportName: string;
  assets: Record<string, string>;
  extraMeshFiles: UsdExportWorkerTransferFile[];
  meshCompression?: UsdMeshCompressionOptions;
  fileFormat?: UsdLayerFileFormat;
  layoutProfile?: UsdPackageLayoutProfile;
}

export interface UsdExportWorkerResultPayload {
  content: string;
  downloadFileName: string;
  archiveFileName: string;
  rootLayerPath: string;
  archiveFiles: UsdExportWorkerTransferFile[];
}

interface SerializedWorkerPayload<TPayload> {
  payload: TPayload;
  transferables: ArrayBuffer[];
}

async function serializeBlobMap(
  files: Map<string, Blob> | undefined,
): Promise<{ files: UsdExportWorkerTransferFile[]; transferables: ArrayBuffer[] }> {
  if (!files || files.size === 0) {
    return {
      files: [],
      transferables: [],
    };
  }

  const serializedFiles = Array.from(files.entries()).map(([path, blob]) => ({
    path,
    blob,
  }));

  return {
    files: serializedFiles,
    transferables: [],
  };
}

function hydrateBlobMap(files: UsdExportWorkerTransferFile[]): Map<string, Blob> {
  return new Map<string, Blob>(files.map((file) => [file.path, file.blob]));
}

export async function serializeUsdExportRequestForWorker(
  options: Omit<ExportRobotToUsdOptions, 'onProgress'>,
): Promise<SerializedWorkerPayload<UsdExportWorkerRequestPayload>> {
  const serializedExtraMeshFiles = await serializeBlobMap(options.extraMeshFiles);

  return {
    payload: {
      robot: options.robot,
      exportName: options.exportName,
      assets: options.assets,
      extraMeshFiles: serializedExtraMeshFiles.files,
      meshCompression: options.meshCompression,
      fileFormat: options.fileFormat,
      layoutProfile: options.layoutProfile,
    },
    transferables: serializedExtraMeshFiles.transferables,
  };
}

export function hydrateUsdExportRequestFromWorker(
  payload: UsdExportWorkerRequestPayload,
): Omit<ExportRobotToUsdOptions, 'onProgress'> {
  const extraMeshFiles = hydrateBlobMap(payload.extraMeshFiles);

  return {
    robot: payload.robot,
    exportName: payload.exportName,
    assets: payload.assets,
    extraMeshFiles: extraMeshFiles.size > 0 ? extraMeshFiles : undefined,
    meshCompression: payload.meshCompression,
    fileFormat: payload.fileFormat,
    layoutProfile: payload.layoutProfile,
  };
}

export async function serializeUsdExportResultForWorker(
  payload: ExportRobotToUsdPayload,
): Promise<SerializedWorkerPayload<UsdExportWorkerResultPayload>> {
  const serializedArchiveFiles = await serializeBlobMap(payload.archiveFiles);

  return {
    payload: {
      content: payload.content,
      downloadFileName: payload.downloadFileName,
      archiveFileName: payload.archiveFileName,
      rootLayerPath: payload.rootLayerPath,
      archiveFiles: serializedArchiveFiles.files,
    },
    transferables: serializedArchiveFiles.transferables,
  };
}

export function hydrateUsdExportResultFromWorker(
  payload: UsdExportWorkerResultPayload,
): ExportRobotToUsdPayload {
  return {
    content: payload.content,
    downloadFileName: payload.downloadFileName,
    archiveFileName: payload.archiveFileName,
    rootLayerPath: payload.rootLayerPath,
    archiveFiles: hydrateBlobMap(payload.archiveFiles),
  };
}

import type {
  PreparedImportBlobFile,
  PreparedDeferredImportAssetFile,
  PreparedImportPayload,
  PreparedImportLibraryFile,
  PreparedImportTextFile,
  PreResolvedImportEntry,
} from './importPreparation';
import type { RobotFile } from '@/types';

export interface PreparedImportTransferFile {
  name: string;
  mimeType: string;
  bytes: ArrayBuffer;
}

export interface PreparedImportWorkerPayload {
  robotFiles: RobotFile[];
  assetFiles: PreparedImportTransferFile[];
  deferredAssetFiles: PreparedDeferredImportAssetFile[];
  usdSourceFiles: PreparedImportTransferFile[];
  libraryFiles: PreparedImportLibraryFile[];
  textFiles: PreparedImportTextFile[];
  preferredFileName: string | null;
  preResolvedImports: PreResolvedImportEntry[];
}

interface SerializedPreparedImportPayload {
  payload: PreparedImportWorkerPayload;
  transferables: ArrayBuffer[];
}

async function serializeTransferFiles(
  files: PreparedImportBlobFile[],
): Promise<{ files: PreparedImportTransferFile[]; transferables: ArrayBuffer[] }> {
  const serializedFiles = await Promise.all(
    files.map(async (file) => {
      const bytes = await file.blob.arrayBuffer();
      return {
        name: file.name,
        mimeType: file.blob.type,
        bytes,
      };
    }),
  );

  return {
    files: serializedFiles,
    transferables: serializedFiles.map((file) => file.bytes),
  };
}

function hydrateTransferFiles(files: PreparedImportTransferFile[]): PreparedImportBlobFile[] {
  return files.map((file) => ({
    name: file.name,
    blob: new Blob([file.bytes], { type: file.mimeType }),
  }));
}

export async function serializePreparedImportPayloadForWorker(
  payload: PreparedImportPayload,
): Promise<SerializedPreparedImportPayload> {
  const [serializedAssetFiles, serializedUsdSourceFiles] = await Promise.all([
    serializeTransferFiles(payload.assetFiles),
    serializeTransferFiles(payload.usdSourceFiles),
  ]);

  return {
    payload: {
      robotFiles: payload.robotFiles,
      assetFiles: serializedAssetFiles.files,
      deferredAssetFiles: payload.deferredAssetFiles,
      usdSourceFiles: serializedUsdSourceFiles.files,
      libraryFiles: payload.libraryFiles,
      textFiles: payload.textFiles,
      preferredFileName: payload.preferredFileName,
      preResolvedImports: payload.preResolvedImports,
    },
    transferables: [
      ...serializedAssetFiles.transferables,
      ...serializedUsdSourceFiles.transferables,
    ],
  };
}

export function hydratePreparedImportPayloadFromWorker(
  payload: PreparedImportWorkerPayload,
): PreparedImportPayload {
  return {
    robotFiles: payload.robotFiles,
    assetFiles: hydrateTransferFiles(payload.assetFiles),
    deferredAssetFiles: payload.deferredAssetFiles,
    usdSourceFiles: hydrateTransferFiles(payload.usdSourceFiles),
    libraryFiles: payload.libraryFiles,
    textFiles: payload.textFiles,
    preferredFileName: payload.preferredFileName,
    preResolvedImports: payload.preResolvedImports,
  };
}

export interface UsdBinaryArchiveTransferFile {
  path: string;
  mimeType: string;
  bytes: ArrayBuffer;
}

export interface UsdBinaryArchiveWorkerPayload {
  files: UsdBinaryArchiveTransferFile[];
}

interface SerializedUsdBinaryArchiveFiles {
  payload: UsdBinaryArchiveWorkerPayload;
  transferables: ArrayBuffer[];
}

async function readBlobBytes(blob: Blob): Promise<ArrayBuffer> {
  if (typeof blob.arrayBuffer === 'function') {
    return await blob.arrayBuffer();
  }

  return await new Response(blob).arrayBuffer();
}

async function serializeUsdBinaryArchiveFile(
  path: string,
  blob: Blob,
): Promise<UsdBinaryArchiveTransferFile> {
  return {
    path,
    mimeType: blob.type,
    bytes: await readBlobBytes(blob),
  };
}

export async function serializeUsdBinaryArchiveFilesForWorker(
  archiveFiles: Map<string, Blob>,
): Promise<SerializedUsdBinaryArchiveFiles> {
  const files = await Promise.all(
    Array.from(archiveFiles.entries()).map(([path, blob]) => serializeUsdBinaryArchiveFile(path, blob)),
  );

  return {
    payload: { files },
    transferables: files.map((file) => file.bytes),
  };
}

export function hydrateUsdBinaryArchiveFilesFromWorker(
  payload: UsdBinaryArchiveWorkerPayload,
): Map<string, Blob> {
  return new Map(
    payload.files.map((file) => [
      file.path,
      new Blob([file.bytes], { type: file.mimeType || '' }),
    ]),
  );
}

export type ProjectArchiveEntryData = string | Uint8Array | ArrayBuffer | Blob;

export type ProjectArchiveTransferFile =
  | {
      path: string;
      kind: 'text';
      text: string;
    }
  | {
      path: string;
      kind: 'bytes';
      bytes: ArrayBuffer;
    }
  | {
      path: string;
      kind: 'blob';
      blob: Blob;
    };

export interface ProjectArchiveWorkerPayload {
  files: ProjectArchiveTransferFile[];
}

export interface ProjectArchiveWorkerResultPayload {
  bytes: ArrayBuffer;
  mimeType: string;
}

interface SerializedProjectArchivePayload<TPayload> {
  payload: TPayload;
  transferables: ArrayBuffer[];
}

function createBytesTransferFile(
  path: string,
  entry: Uint8Array | ArrayBuffer,
): { file: ProjectArchiveTransferFile; transferables: ArrayBuffer[] } {
  const bytes =
    entry instanceof Uint8Array
      ? entry.byteOffset === 0 && entry.byteLength === entry.buffer.byteLength
        ? entry.buffer
        : entry.buffer.slice(entry.byteOffset, entry.byteOffset + entry.byteLength)
      : entry;

  return {
    file: {
      path,
      kind: 'bytes',
      bytes,
    },
    transferables: [bytes],
  };
}

export async function serializeProjectArchiveEntriesForWorker(
  entries: Map<string, ProjectArchiveEntryData>,
): Promise<SerializedProjectArchivePayload<ProjectArchiveWorkerPayload>> {
  const files: ProjectArchiveTransferFile[] = [];
  const transferables: ArrayBuffer[] = [];

  entries.forEach((entry, path) => {
    if (typeof entry === 'string') {
      files.push({
        path,
        kind: 'text',
        text: entry,
      });
      return;
    }

    if (entry instanceof Uint8Array || entry instanceof ArrayBuffer) {
      const transferFile = createBytesTransferFile(path, entry);
      files.push(transferFile.file);
      transferables.push(...transferFile.transferables);
      return;
    }

    files.push({
      path,
      kind: 'blob',
      blob: entry,
    });
  });

  return {
    payload: { files },
    transferables,
  };
}

export function hydrateProjectArchiveEntriesFromWorker(
  payload: ProjectArchiveWorkerPayload,
): Map<string, ProjectArchiveEntryData> {
  const entries = new Map<string, ProjectArchiveEntryData>();
  payload.files.forEach((file) => {
    switch (file.kind) {
      case 'text':
        entries.set(file.path, file.text);
        break;
      case 'blob':
        entries.set(file.path, file.blob);
        break;
      case 'bytes':
      default:
        entries.set(file.path, file.bytes);
        break;
    }
  });
  return entries;
}

export function hydrateProjectArchiveBlobFromWorker(
  payload: ProjectArchiveWorkerResultPayload,
): Blob {
  return new Blob([payload.bytes], {
    type: payload.mimeType || 'application/zip',
  });
}

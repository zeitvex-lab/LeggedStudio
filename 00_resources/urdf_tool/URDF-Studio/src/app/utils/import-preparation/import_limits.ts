interface ImportLimitEntry {
  path: string;
  size: number;
}

type ImportLimitFileInput = File | { file: File; relativePath?: string };

const MAX_IMPORT_FILE_COUNT = 2_000;
const MAX_IMPORT_TOTAL_BYTES = 512 * 1024 * 1024;
const MAX_IMPORT_SINGLE_FILE_BYTES = 512 * 1024 * 1024;
const MAX_IMPORT_PATH_DEPTH = 32;

function normalizeImportLimitPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\/+/, '');
}

function resolveImportLimitInputFile(input: ImportLimitFileInput): File {
  return input instanceof File ? input : input.file;
}

function resolveImportLimitInputPath(input: ImportLimitFileInput): string {
  if (!(input instanceof File) && input.relativePath) {
    return input.relativePath;
  }

  const file = resolveImportLimitInputFile(input);
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

export function assertImportEntriesWithinLimits(
  entries: readonly ImportLimitEntry[],
  label: string,
): void {
  if (entries.length > MAX_IMPORT_FILE_COUNT) {
    throw new Error(
      `${label} contains too many files (${entries.length}). Maximum: ${MAX_IMPORT_FILE_COUNT}.`,
    );
  }

  let totalBytes = 0;
  for (const entry of entries) {
    totalBytes += entry.size;
    if (entry.size > MAX_IMPORT_SINGLE_FILE_BYTES) {
      throw new Error(
        `${label} file "${entry.path}" is too large (${entry.size} bytes). `
          + `Maximum: ${MAX_IMPORT_SINGLE_FILE_BYTES} bytes.`,
      );
    }

    const depth = normalizeImportLimitPath(entry.path).split('/').filter(Boolean).length;
    if (depth > MAX_IMPORT_PATH_DEPTH) {
      throw new Error(
        `${label} file "${entry.path}" is nested too deeply (${depth} levels). `
          + `Maximum: ${MAX_IMPORT_PATH_DEPTH}.`,
      );
    }
  }

  if (totalBytes > MAX_IMPORT_TOTAL_BYTES) {
    throw new Error(
      `${label} is too large (${totalBytes} bytes). Maximum: ${MAX_IMPORT_TOTAL_BYTES} bytes.`,
    );
  }
}

export function assertDeferredImportAssetsWithinLimits(
  archiveEntries: readonly ImportLimitEntry[],
  assetFiles: ReadonlyArray<{ sourcePath: string }>,
): void {
  const archiveEntriesByPath = new Map(archiveEntries.map((entry) => [entry.path, entry]));
  assertImportEntriesWithinLimits(
    assetFiles.map((file) => ({
      path: file.sourcePath,
      size: archiveEntriesByPath.get(file.sourcePath)?.size ?? 0,
    })),
    'Deferred archive asset hydration',
  );
}

export function assertLooseImportFilesWithinLimits(files: readonly ImportLimitFileInput[]): void {
  assertImportEntriesWithinLimits(
    files.map((input) => ({
      path: resolveImportLimitInputPath(input),
      size: resolveImportLimitInputFile(input).size,
    })),
    'Import',
  );
}

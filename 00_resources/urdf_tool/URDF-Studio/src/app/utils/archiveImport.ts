import { isSupportedArchiveImportFile } from '@/shared/utils/robotFileSupport';

export interface ArchiveImportEntry {
  path: string;
  name: string;
  size: number;
  lastModified: number;
}

export interface ArchiveExtractionSnapshot {
  processedEntries: number;
  totalEntries: number;
  processedBytes: number;
  totalBytes: number;
}

export interface ArchiveImportSession {
  entries: ArchiveImportEntry[];
  extractEntries: (
    requestedPaths: readonly string[],
    onProgress?: (snapshot: ArchiveExtractionSnapshot) => void,
  ) => Promise<Array<{ path: string; file: File; size: number }>>;
}

interface ArchiveReaderEntryLike {
  name?: string;
  size?: number;
  lastModified?: number;
}

interface ArchiveFilesArrayEntryLike {
  file?: ArchiveReaderEntryLike | null;
  path?: string;
}

interface ExtractedArchiveContentDirectory {
  [key: string]: ExtractedArchiveContentNode;
}

type ExtractedArchiveContentNode = File | ExtractedArchiveContentDirectory | null;

interface ArchiveReaderLike {
  getFilesArray(): Promise<ArchiveFilesArrayEntryLike[]>;
  extractSingleFile(path: string): Promise<File>;
  extractFiles(
    onEntryExtracted?: (entry: { file: File; path: string }) => void,
  ): Promise<ExtractedArchiveContentNode>;
  close(): Promise<void>;
}

interface ArchiveModuleLike {
  Archive: {
    init(options?: { getWorker?: () => Worker; workerUrl?: string } | null): unknown;
    open(file: File): Promise<ArchiveReaderLike>;
  };
}

let archiveModulePromise: Promise<ArchiveModuleLike> | null = null;
let archiveModuleInitialized = false;
// Browser builds need an explicit worker URL because Vite prebundles the ESM entry
// under /node_modules/.vite/deps, which breaks libarchive's default relative lookup.
const NODE_ARCHIVE_MODULE_SPECIFIER = 'libarchive.js/dist/libarchive-node.mjs';
const BROWSER_ARCHIVE_WORKER_URL = '/assets/worker-bundle.js';
const MIN_FULL_ARCHIVE_EXTRACTION_ENTRIES = 8;
const FULL_ARCHIVE_EXTRACTION_ENTRY_RATIO = 0.55;
const FULL_ARCHIVE_EXTRACTION_BYTES_RATIO = 0.6;
const CUMULATIVE_FULL_ARCHIVE_EXTRACTION_ENTRY_RATIO = 0.4;
const CUMULATIVE_FULL_ARCHIVE_EXTRACTION_BYTES_RATIO = 0.45;
const EAGER_FULL_ARCHIVE_EXTRACTION_MAX_ENTRIES = 48;
const EAGER_FULL_ARCHIVE_EXTRACTION_MAX_TOTAL_BYTES = 48 * 1024 * 1024;

function isNodeRuntime(): boolean {
  return typeof process !== 'undefined' && Boolean(process.versions?.node);
}

function normalizeArchiveEntryPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+/g, '/');
}

function resolveArchiveEntryPath(entry: ArchiveFilesArrayEntryLike): string | null {
  const fileName = typeof entry.file?.name === 'string' ? entry.file.name : '';
  if (!fileName) {
    return null;
  }

  const normalizedPath = normalizeArchiveEntryPath(`${entry.path || ''}${fileName}`);
  return normalizedPath || null;
}

async function loadArchiveModule(): Promise<ArchiveModuleLike> {
  if (!archiveModulePromise) {
    archiveModulePromise = isNodeRuntime()
      ? import(
          /* @vite-ignore */
          NODE_ARCHIVE_MODULE_SPECIFIER
        )
      : import('libarchive.js');
  }

  const archiveModule = await archiveModulePromise;
  if (!isNodeRuntime() && !archiveModuleInitialized) {
    archiveModule.Archive.init({
      workerUrl: BROWSER_ARCHIVE_WORKER_URL,
    });
    archiveModuleInitialized = true;
  }
  return archiveModule;
}

async function withArchiveReader<T>(
  archiveFile: File,
  action: (reader: ArchiveReaderLike) => Promise<T>,
): Promise<T> {
  const archiveModule = await loadArchiveModule();
  const reader = await archiveModule.Archive.open(archiveFile);
  let actionResult!: T;
  let actionError: unknown = null;

  try {
    actionResult = await action(reader);
  } catch (error) {
    actionError = error;
  }

  try {
    await reader.close();
  } catch (closeError) {
    if (actionError) {
      console.error(
        '[archiveImport] Failed to close archive reader after action failure.',
        closeError,
      );
      throw actionError;
    }
    throw closeError;
  }

  if (actionError) {
    throw actionError;
  }

  return actionResult;
}

async function listArchiveEntriesFromReader(
  reader: ArchiveReaderLike,
): Promise<ArchiveImportEntry[]> {
  const entries = await reader.getFilesArray();

  return entries
    .map((entry) => {
      const path = resolveArchiveEntryPath(entry);
      if (!path) {
        return null;
      }

      return {
        path,
        name: entry.file?.name || path.split('/').pop() || path,
        size: Number(entry.file?.size || 0),
        lastModified: Number(entry.file?.lastModified || 0),
      } satisfies ArchiveImportEntry;
    })
    .filter((entry): entry is ArchiveImportEntry => Boolean(entry));
}

function normalizeRequestedArchivePaths(requestedPaths: readonly string[]): string[] {
  return Array.from(
    new Set(
      requestedPaths
        .map((path) => normalizeArchiveEntryPath(path))
        .filter((path) => path.length > 0),
    ),
  );
}

function flattenExtractedArchiveContent(
  node: ExtractedArchiveContentNode,
  parentPath = '',
): Array<{ path: string; file: File }> {
  if (node instanceof File) {
    return parentPath ? [{ path: parentPath, file: node }] : [];
  }

  if (!node || typeof node !== 'object') {
    return [];
  }

  return Object.entries(node).flatMap(([segment, childNode]) =>
    flattenExtractedArchiveContent(childNode, parentPath ? `${parentPath}/${segment}` : segment),
  );
}

function shouldExtractWholeArchive(
  requestedPaths: readonly string[],
  entries: readonly ArchiveImportEntry[],
  entryMap: ReadonlyMap<string, ArchiveImportEntry>,
  options: {
    entryRatioThreshold?: number;
    bytesRatioThreshold?: number;
  } = {},
): boolean {
  if (requestedPaths.length < MIN_FULL_ARCHIVE_EXTRACTION_ENTRIES || entries.length === 0) {
    return false;
  }

  const {
    entryRatioThreshold = FULL_ARCHIVE_EXTRACTION_ENTRY_RATIO,
    bytesRatioThreshold = FULL_ARCHIVE_EXTRACTION_BYTES_RATIO,
  } = options;

  const totalEntries = entries.length;
  const requestedEntryRatio = requestedPaths.length / totalEntries;
  if (requestedEntryRatio >= entryRatioThreshold) {
    return true;
  }

  const totalBytes = entries.reduce((sum, entry) => sum + entry.size, 0);
  if (totalBytes <= 0) {
    return false;
  }

  const requestedBytes = requestedPaths.reduce(
    (sum, path) => sum + (entryMap.get(path)?.size || 0),
    0,
  );
  return requestedBytes / totalBytes >= bytesRatioThreshold;
}

function shouldEagerlyExtractWholeArchive(entries: readonly ArchiveImportEntry[]): boolean {
  if (entries.length === 0 || entries.length > EAGER_FULL_ARCHIVE_EXTRACTION_MAX_ENTRIES) {
    return false;
  }

  const totalBytes = entries.reduce((sum, entry) => sum + entry.size, 0);
  return totalBytes > 0 && totalBytes <= EAGER_FULL_ARCHIVE_EXTRACTION_MAX_TOTAL_BYTES;
}

export async function withArchiveImportSession<T>(
  archiveFile: File,
  action: (session: ArchiveImportSession) => Promise<T>,
): Promise<T> {
  return withArchiveReader(archiveFile, async (reader) => {
    const entries = await listArchiveEntriesFromReader(reader);
    const entryMap = new Map(entries.map((entry) => [entry.path, entry] as const));
    const eagerlyExtractWholeArchive = shouldEagerlyExtractWholeArchive(entries);
    const requestedPathHistory = new Set<string>();
    const extractedFileCache = new Map<string, { path: string; file: File; size: number }>();
    let fullyExtractedEntryMap: Map<string, { path: string; file: File; size: number }> | null =
      null;

    const emitArchiveExtractionProgress = (
      requestedPaths: readonly string[],
      entryMapForProgress: ReadonlyMap<string, { size: number }>,
      onProgress?: (snapshot: ArchiveExtractionSnapshot) => void,
    ): void => {
      if (!onProgress) {
        return;
      }

      const totalBytes = requestedPaths.reduce(
        (sum, path) => sum + (entryMapForProgress.get(path)?.size || 0),
        0,
      );
      let processedEntries = 0;
      let processedBytes = 0;

      onProgress({
        processedEntries,
        totalEntries: requestedPaths.length,
        processedBytes,
        totalBytes,
      });

      requestedPaths.forEach((path) => {
        processedEntries += 1;
        processedBytes += entryMapForProgress.get(path)?.size || 0;
        onProgress({
          processedEntries,
          totalEntries: requestedPaths.length,
          processedBytes,
          totalBytes,
        });
      });
    };

    const ensureFullyExtractedEntries = async (): Promise<
      Map<string, { path: string; file: File; size: number }>
    > => {
      if (fullyExtractedEntryMap) {
        return fullyExtractedEntryMap;
      }

      const extractedEntries = flattenExtractedArchiveContent(await reader.extractFiles());
      fullyExtractedEntryMap = new Map([
        ...extractedFileCache,
        ...extractedEntries.flatMap((entry) => {
          const path = normalizeArchiveEntryPath(entry.path);
          if (!path) {
            return [];
          }

          const extractedEntry = {
            path,
            file: entry.file,
            size: entryMap.get(path)?.size || entry.file.size,
          };
          extractedFileCache.set(path, extractedEntry);

          return [[path, extractedEntry] as const];
        }),
      ]);

      return fullyExtractedEntryMap;
    };

    return action({
      entries,
      extractEntries: async (requestedPaths, onProgress) => {
        const normalizedRequestedPaths = normalizeRequestedArchivePaths(requestedPaths);

        if (normalizedRequestedPaths.length === 0) {
          onProgress?.({
            processedEntries: 0,
            totalEntries: 0,
            processedBytes: 0,
            totalBytes: 0,
          });
          return [];
        }

        normalizedRequestedPaths.forEach((path) => {
          if (!entryMap.has(path)) {
            throw new Error(`Missing deferred asset "${path}" in archive.`);
          }
        });

        const cachedPaths = normalizedRequestedPaths.filter((path) => extractedFileCache.has(path));
        if (cachedPaths.length === normalizedRequestedPaths.length) {
          emitArchiveExtractionProgress(normalizedRequestedPaths, entryMap, onProgress);
          normalizedRequestedPaths.forEach((path) => requestedPathHistory.add(path));
          return normalizedRequestedPaths.map((path) => {
            const cachedEntry = extractedFileCache.get(path);
            if (!cachedEntry) {
              throw new Error(`Missing deferred asset "${path}" in archive cache.`);
            }
            return cachedEntry;
          });
        }

        const cumulativeRequestedPaths = Array.from(
          new Set([...requestedPathHistory, ...normalizedRequestedPaths]),
        );

        if (
          fullyExtractedEntryMap ||
          eagerlyExtractWholeArchive ||
          shouldExtractWholeArchive(normalizedRequestedPaths, entries, entryMap) ||
          shouldExtractWholeArchive(cumulativeRequestedPaths, entries, entryMap, {
            entryRatioThreshold: CUMULATIVE_FULL_ARCHIVE_EXTRACTION_ENTRY_RATIO,
            bytesRatioThreshold: CUMULATIVE_FULL_ARCHIVE_EXTRACTION_BYTES_RATIO,
          })
        ) {
          const extractedEntryMap = await ensureFullyExtractedEntries();
          const extractedFiles = normalizedRequestedPaths.map((path) => {
            const extractedEntry = extractedEntryMap.get(path);
            if (!extractedEntry) {
              throw new Error(`Missing deferred asset "${path}" in archive.`);
            }

            return extractedEntry;
          });

          emitArchiveExtractionProgress(normalizedRequestedPaths, entryMap, onProgress);
          normalizedRequestedPaths.forEach((path) => requestedPathHistory.add(path));
          return extractedFiles;
        }

        const uncachedPaths = normalizedRequestedPaths.filter(
          (path) => !extractedFileCache.has(path),
        );
        const totalBytes = uncachedPaths.reduce(
          (sum, path) => sum + (entryMap.get(path)?.size || 0),
          0,
        );
        let processedEntries = 0;
        let processedBytes = 0;
        onProgress?.({
          processedEntries,
          totalEntries: uncachedPaths.length,
          processedBytes,
          totalBytes,
        });

        for (const path of uncachedPaths) {
          const file = await reader.extractSingleFile(path);
          const size = entryMap.get(path)?.size || file.size;
          extractedFileCache.set(path, { path, file, size });

          requestedPathHistory.add(path);
          processedEntries += 1;
          processedBytes += size;
          onProgress?.({
            processedEntries,
            totalEntries: uncachedPaths.length,
            processedBytes,
            totalBytes,
          });
        }

        return normalizedRequestedPaths.map((path) => {
          const cachedEntry = extractedFileCache.get(path);
          if (!cachedEntry) {
            throw new Error(`Missing deferred asset "${path}" after archive extraction.`);
          }
          return cachedEntry;
        });
      },
    });
  });
}

export { isSupportedArchiveImportFile };

import { ensureUsdWasmRuntime } from '@/features/editor/usd_runtime';

type BinaryReadyUsdLayer = {
  Export?: (...args: unknown[]) => unknown;
  delete?: () => void;
};

type BinaryReadyUsdModule = Awaited<ReturnType<typeof ensureUsdWasmRuntime>>['USD'] & {
  FS_readFile?: (path: string, opts?: { encoding?: 'utf8'; flags?: string }) => Uint8Array | string;
  FS_writeFile?: (
    path: string,
    data: string | ArrayLike<number> | ArrayBufferView,
    opts?: { flags?: string },
  ) => void;
  SdfLayer?: {
    FindOrOpen?: (path: string, args?: Record<string, string>) => BinaryReadyUsdLayer | null;
  };
};

export type BinaryReadyUsdRuntime = Pick<Awaited<ReturnType<typeof ensureUsdWasmRuntime>>, 'USD'>;

const USDC_FILE_FORMAT_ARGS = { format: 'usdc' } as const;

function isUsdLayerPath(path: string): boolean {
  return /\.usd$/i.test(path);
}

function createFsRoot(label: string): string {
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  // Use relative virtual filesystem paths so crate export preserves authored
  // relative asset references like "../assets/foo.png" instead of rewriting
  // them to absolute "/tmp/..." paths inside the WASM sandbox.
  return `tmp/${label}-${suffix}`;
}

function ensureVirtualDirectory(module: BinaryReadyUsdModule, absoluteDirectoryPath: string): void {
  const normalized = absoluteDirectoryPath
    .replace(/\\/g, '/')
    .replace(/\/+/g, '/')
    .replace(/\/$/, '');
  if (!normalized || normalized === '/') return;

  let parent = '/';
  for (const segment of normalized.split('/').filter(Boolean)) {
    try {
      module.FS_createPath?.(parent, segment, true, true);
    } catch {
      // Directory creation is idempotent in our usage; ignore collisions.
    }
    parent = parent === '/' ? `/${segment}` : `${parent}/${segment}`;
  }
}

function dirname(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  const lastSlash = normalized.lastIndexOf('/');
  return lastSlash > 0 ? normalized.slice(0, lastSlash) : '/';
}

function joinFsPath(root: string, relativePath: string): string {
  const normalizedRelative = relativePath.replace(/\\/g, '/').replace(/^\/+/, '');
  return `${root}/${normalizedRelative}`;
}

function toBinaryBlob(data: Uint8Array | string): Blob {
  return typeof data === 'string'
    ? new Blob([data], { type: 'application/octet-stream' })
    : new Blob([data], { type: 'application/octet-stream' });
}

function readUsdMagic(data: Uint8Array | string): string {
  if (typeof data === 'string') {
    return data.slice(0, 8);
  }

  return new TextDecoder('latin1').decode(data.slice(0, 8));
}

function readUsdFileFromFs(
  module: BinaryReadyUsdModule,
  absolutePath: string,
): Uint8Array | string | null {
  try {
    const data = module.FS_readFile?.(absolutePath);
    return data instanceof Uint8Array || typeof data === 'string' ? data : null;
  } catch {
    return null;
  }
}

function isUsdCrateFile(data: Uint8Array | string | null | undefined): boolean {
  return data != null && readUsdMagic(data).startsWith('PXR-USDC');
}

function describeExportAttemptFailure(label: string, error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return `${label}: ${message || 'unknown error'}`;
}

function exportUsdLayerAsCrate(
  module: BinaryReadyUsdModule,
  sourceFsPath: string,
  targetFsPath: string,
): void {
  const failedAttempts: string[] = [];
  const layer = module.SdfLayer?.FindOrOpen?.(sourceFsPath, {});

  if (!layer || typeof layer.Export !== 'function') {
    throw new Error(`USD runtime does not expose SdfLayer.FindOrOpen/Export: ${sourceFsPath}`);
  }

  try {
    const result = layer.Export(targetFsPath, '', USDC_FILE_FORMAT_ARGS);
    if (result === false) {
      failedAttempts.push('SdfLayer Export(path, "", { format: "usdc" }): returned false');
    }
  } catch (error) {
    failedAttempts.push(
      describeExportAttemptFailure('SdfLayer Export(path, "", { format: "usdc" })', error),
    );
  } finally {
    if (typeof layer.delete === 'function') {
      layer.delete();
    }
    module.flushPendingDeletes?.();
  }

  if (isUsdCrateFile(readUsdFileFromFs(module, targetFsPath))) {
    return;
  }
  failedAttempts.push(
    'SdfLayer Export(path, "", { format: "usdc" }): did not produce a binary USD crate',
  );

  const attemptDetail =
    failedAttempts.length > 0 ? ` Attempts failed: ${failedAttempts.join('; ')}` : '';
  throw new Error(`Failed to export binary USD crate layer: ${targetFsPath}.${attemptDetail}`);
}

export async function convertUsdArchiveFilesToBinaryCore(
  archiveFiles: Map<string, Blob>,
  options: {
    onProgress?: (progress: { current: number; total: number; filePath: string }) => void;
    loadRuntime?: () => Promise<BinaryReadyUsdRuntime>;
  } = {},
): Promise<Map<string, Blob>> {
  const { onProgress, loadRuntime } = options;
  const runtime = await (loadRuntime?.() ?? ensureUsdWasmRuntime());
  const USD = runtime.USD as BinaryReadyUsdModule;

  if (
    typeof USD.FS_createPath !== 'function' ||
    typeof USD.FS_writeFile !== 'function' ||
    typeof USD.FS_readFile !== 'function' ||
    typeof USD.SdfLayer?.FindOrOpen !== 'function'
  ) {
    throw new Error('USD binary export runtime is unavailable.');
  }

  const sourceRoot = createFsRoot('urdf-studio-usd-src');
  const targetRoot = createFsRoot('urdf-studio-usd-bin');
  const usdLayerPaths = Array.from(archiveFiles.keys()).filter(isUsdLayerPath);
  const totalUsdLayers = usdLayerPaths.length;
  const binaryFiles = new Map<string, Blob>();
  const cleanupFilePaths = new Set<string>();

  try {
    ensureVirtualDirectory(USD, sourceRoot);
    ensureVirtualDirectory(USD, targetRoot);

    for (const [relativePath, blob] of archiveFiles) {
      if (!isUsdLayerPath(relativePath)) {
        binaryFiles.set(relativePath, blob);
        continue;
      }

      const sourceFsPath = joinFsPath(sourceRoot, relativePath);
      ensureVirtualDirectory(USD, dirname(sourceFsPath));
      USD.FS_writeFile(sourceFsPath, new Uint8Array(await blob.arrayBuffer()));
      cleanupFilePaths.add(sourceFsPath);
    }

    for (const [index, relativePath] of usdLayerPaths.entries()) {
      onProgress?.({
        current: index + 1,
        total: totalUsdLayers,
        filePath: relativePath,
      });
      const sourceFsPath = joinFsPath(sourceRoot, relativePath);
      const targetFsPath = joinFsPath(targetRoot, relativePath);
      ensureVirtualDirectory(USD, dirname(targetFsPath));

      // Convert the authored SdfLayer directly. Using UsdStage.Export composes
      // references/sublayers and can balloon small layer files into huge crates.
      exportUsdLayerAsCrate(USD, sourceFsPath, targetFsPath);

      const binaryData = USD.FS_readFile(targetFsPath);
      if (!(binaryData instanceof Uint8Array) && typeof binaryData !== 'string') {
        throw new Error(`Failed to read binary USD layer: ${relativePath}`);
      }

      binaryFiles.set(relativePath, toBinaryBlob(binaryData));
      cleanupFilePaths.add(targetFsPath);
    }

    return binaryFiles;
  } finally {
    for (const filePath of cleanupFilePaths) {
      try {
        USD.FS_unlink?.(filePath);
      } catch {
        // Best-effort cleanup of temporary virtual filesystem files.
      }
    }
    USD.flushPendingDeletes?.();
  }
}

export async function convertUsdArchiveFilesToBinary(
  archiveFiles: Map<string, Blob>,
  options: {
    onProgress?: (progress: { current: number; total: number; filePath: string }) => void;
    loadRuntime?: () => Promise<BinaryReadyUsdRuntime>;
  } = {},
): Promise<Map<string, Blob>> {
  if (typeof document === 'undefined') {
    return archiveFiles;
  }

  return convertUsdArchiveFilesToBinaryCore(archiveFiles, options);
}

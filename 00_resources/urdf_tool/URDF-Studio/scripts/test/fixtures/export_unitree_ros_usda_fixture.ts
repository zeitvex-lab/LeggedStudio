#!/usr/bin/env node

import fsPromises from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { JSDOM } from 'jsdom';

import { parseColladaSceneData } from '@/core/loaders/colladaWorkerSceneData';
import { disposeColladaParseWorkerPoolClient } from '@/core/loaders/colladaParseWorkerBridge';
import { disposeObjParseWorkerPoolClient } from '@/core/loaders/objParseWorkerBridge';
import { parseObjModelDataFromBytes } from '@/core/loaders/objWasmParser';
import { parseURDF } from '@/core/parsers/urdf/parser';
import { disposeStlParseWorkerPoolClient } from '@/core/loaders/stlParseWorkerBridge';
import { parseStlGeometryData } from '@/core/loaders/stlGeometryData';
import { exportRobotToUsd } from '@/features/file-io/utils/usdExportCoordinator';

type ManifestRecord = {
  source_urdf: string;
  output_usda: string;
  status?: string | null;
  robot_path?: string | null;
  default_prim?: string | null;
  error?: string | null;
};

type ManifestFile = {
  records?: ManifestRecord[];
};

type Options = {
  manifestPath: string;
  match: string[];
  outputUsda: string | null;
  sourceUrdf: string | null;
  dryRun: boolean;
  meshQuality: number;
};

type WorkerMessageHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;

const DEFAULT_MANIFEST_PATH = path.resolve('test/unitree_ros_usda/export-manifest.json');
const DEFAULT_MESH_QUALITY = 50;
const ASSET_EXTENSIONS = new Set([
  '.dae',
  '.obj',
  '.stl',
  '.gltf',
  '.glb',
  '.png',
  '.jpg',
  '.jpeg',
  '.bmp',
  '.gif',
  '.webp',
  '.mtl',
  '.svg',
]);

class FakeColladaWorker {
  private readonly listeners = new Map<string, Set<WorkerMessageHandler>>();

  addEventListener(type: string, handler: WorkerMessageHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerMessageHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerMessageHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown): void {
    const request = message as { type?: string; assetUrl?: string; requestId?: number };
    if (!request?.assetUrl || !Number.isFinite(request.requestId)) {
      return;
    }

    void (async () => {
      try {
        const response = await fetch(request.assetUrl);
        if (!response.ok) {
          throw new Error(
            `Failed to fetch Collada asset: ${response.status} ${response.statusText}`,
          );
        }

        if (request.type === 'parse-collada') {
          const colladaText = await response.text();
          const result = withSuppressedColladaConsole(() =>
            parseColladaSceneData(colladaText, request.assetUrl),
          );
          this.emitMessage({
            type: 'parse-collada-result',
            requestId: request.requestId,
            result,
          });
          return;
        }

        if (request.type === 'parse-stl') {
          this.emitMessage({
            type: 'parse-stl-result',
            requestId: request.requestId,
            result: parseStlGeometryData(await response.arrayBuffer()),
          });
          return;
        }

        if (request.type === 'parse-obj') {
          this.emitMessage({
            type: 'parse-obj-result',
            requestId: request.requestId,
            result: await parseObjModelDataFromBytes(await response.arrayBuffer()),
          });
        }
      } catch (error) {
        const workerError = error instanceof Error ? error : new Error(String(error));
        this.emitMessage({
          type:
            request.type === 'parse-stl'
              ? 'parse-stl-error'
              : request.type === 'parse-obj'
                ? 'parse-obj-error'
                : 'parse-collada-error',
          requestId: request.requestId,
          error: workerError.message,
        });
      }
    })();
  }

  terminate(): void {}

  private emitMessage(data: unknown): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data });
    });
  }
}

function withSuppressedColladaConsole<T>(run: () => T): T {
  const originalLog = console.log;
  const originalInfo = console.info;
  const originalWarn = console.warn;
  const isColladaNoise = (value: unknown) => String(value || '').includes('THREE.ColladaLoader');

  console.log = (...args: unknown[]) => {
    if (!isColladaNoise(args[0])) {
      originalLog(...args);
    }
  };
  console.info = (...args: unknown[]) => {
    if (!isColladaNoise(args[0])) {
      originalInfo(...args);
    }
  };
  console.warn = (...args: unknown[]) => {
    if (!isColladaNoise(args[0])) {
      originalWarn(...args);
    }
  };

  try {
    return run();
  } finally {
    console.log = originalLog;
    console.info = originalInfo;
    console.warn = originalWarn;
  }
}

function normalizePath(value: string): string {
  return value.replace(/\\/g, '/').replace(/^\/+/, '');
}

function printHelp(): void {
  process.stdout.write(`Usage:
  npx tsx scripts/test/fixtures/export_unitree_ros_usda_fixture.ts [options]

Options:
  --manifest <path>        Manifest JSON path. Default: ${DEFAULT_MANIFEST_PATH}
  --match <text>           Match records by source/output path substring. Repeatable.
  --output-usda <path>     Export only the record whose output_usda matches this path.
  --source-urdf <path>     Export only the record whose source_urdf matches this path.
  --mesh-quality <0-100>   Mesh compression quality. Default: ${DEFAULT_MESH_QUALITY}
  --dry-run                Resolve and export, but do not overwrite fixture files.
  --help                   Show this help.
`);
}

function fail(message: string): never {
  throw new Error(message);
}

function parseInteger(value: string, flagName: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
    fail(`Invalid value for ${flagName}: ${value}`);
  }
  return parsed;
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    manifestPath: DEFAULT_MANIFEST_PATH,
    match: [],
    outputUsda: null,
    sourceUrdf: null,
    dryRun: false,
    meshQuality: DEFAULT_MESH_QUALITY,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (value == null) {
        fail(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--manifest':
        options.manifestPath = path.resolve(nextValue());
        break;
      case '--match':
        options.match.push(nextValue());
        break;
      case '--output-usda':
        options.outputUsda = normalizePath(nextValue());
        break;
      case '--source-urdf':
        options.sourceUrdf = normalizePath(nextValue());
        break;
      case '--mesh-quality':
        options.meshQuality = parseInteger(nextValue(), '--mesh-quality');
        break;
      case '--dry-run':
        options.dryRun = true;
        break;
      case '--help':
      case '-h':
        printHelp();
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function collectAssetFiles(
  rootDir: string,
  baseDir: string = rootDir,
): Promise<Array<{ absolutePath: string; relativePath: string }>> {
  const results: Array<{ absolutePath: string; relativePath: string }> = [];
  const entries = await fsPromises.readdir(rootDir, { withFileTypes: true });
  entries.sort((left, right) => left.name.localeCompare(right.name));

  for (const entry of entries) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await collectAssetFiles(absolutePath, baseDir)));
      continue;
    }

    if (!entry.isFile()) {
      continue;
    }

    if (!ASSET_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      continue;
    }

    results.push({
      absolutePath,
      relativePath: normalizePath(path.relative(baseDir, absolutePath)),
    });
  }

  return results;
}

function getMimeType(absolutePath: string): string {
  switch (path.extname(absolutePath).toLowerCase()) {
    case '.dae':
      return 'text/xml';
    case '.stl':
      return 'model/stl';
    case '.obj':
      return 'text/plain';
    case '.gltf':
      return 'model/gltf+json';
    case '.glb':
      return 'model/gltf-binary';
    case '.png':
      return 'image/png';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.bmp':
      return 'image/bmp';
    case '.gif':
      return 'image/gif';
    case '.webp':
      return 'image/webp';
    case '.mtl':
      return 'text/plain';
    default:
      return 'application/octet-stream';
  }
}

async function buildAssetMap(assetRootAbsolute: string): Promise<Record<string, string>> {
  const packageName = path.basename(assetRootAbsolute);
  const assets: Record<string, string> = {};
  const assetFiles = await collectAssetFiles(assetRootAbsolute);

  for (const { absolutePath, relativePath } of assetFiles) {
    const dataUrl = `data:${getMimeType(absolutePath)};base64,${(
      await fsPromises.readFile(absolutePath)
    ).toString('base64')}`;

    for (const alias of [
      relativePath,
      `${packageName}/${relativePath}`,
      `package://${packageName}/${relativePath}`,
      path.basename(relativePath),
    ]) {
      assets[alias] = dataUrl;
    }
  }

  return assets;
}

async function readManifest(manifestPath: string): Promise<ManifestRecord[]> {
  const parsed = JSON.parse(await fsPromises.readFile(manifestPath, 'utf8')) as ManifestFile;
  if (!Array.isArray(parsed.records)) {
    fail(`Manifest does not contain a "records" array: ${manifestPath}`);
  }
  return parsed.records;
}

function inferAssetRoot(sourceUrdfAbsolute: string): string {
  return path.dirname(path.dirname(sourceUrdfAbsolute));
}

function selectRecords(records: ManifestRecord[], options: Options): ManifestRecord[] {
  return records.filter((record) => {
    const outputUsda = normalizePath(record.output_usda);
    const sourceUrdf = normalizePath(record.source_urdf);

    if (options.outputUsda && outputUsda !== options.outputUsda) {
      return false;
    }

    if (options.sourceUrdf && sourceUrdf !== options.sourceUrdf) {
      return false;
    }

    if (options.match.length > 0) {
      const haystack = `${sourceUrdf}\n${outputUsda}`.toLowerCase();
      return options.match.every((pattern) => haystack.includes(pattern.toLowerCase()));
    }

    return true;
  });
}

function stripLeadingArchiveRoot(relativeArchivePath: string): string {
  const normalized = normalizePath(relativeArchivePath);
  const segments = normalized.split('/');
  return normalizePath(segments.slice(1).join('/'));
}

async function writeExportedArchive(
  record: ManifestRecord,
  archiveFiles: Map<string, Blob>,
  dryRun: boolean,
): Promise<{
  outputRoot: string;
  writtenFiles: string[];
}> {
  const outputUsdaAbsolute = path.resolve(record.output_usda);
  const outputRoot = path.dirname(outputUsdaAbsolute);
  const writtenFiles: string[] = [];

  if (dryRun) {
    for (const [archiveRelativePath] of archiveFiles) {
      writtenFiles.push(path.join(outputRoot, stripLeadingArchiveRoot(archiveRelativePath)));
    }
    return { outputRoot, writtenFiles };
  }

  await fsPromises.rm(outputRoot, { recursive: true, force: true });
  await fsPromises.mkdir(outputRoot, { recursive: true });

  for (const [archiveRelativePath, blob] of archiveFiles) {
    const relativeTargetPath = stripLeadingArchiveRoot(archiveRelativePath);
    if (!relativeTargetPath) {
      continue;
    }

    const targetPath = path.join(outputRoot, relativeTargetPath);
    await fsPromises.mkdir(path.dirname(targetPath), { recursive: true });
    await fsPromises.writeFile(targetPath, Buffer.from(await blob.arrayBuffer()));
    writtenFiles.push(targetPath);
  }

  return { outputRoot, writtenFiles };
}

async function exportRecord(record: ManifestRecord, options: Options) {
  const sourceUrdfAbsolute = path.resolve(record.source_urdf);
  const assetRootAbsolute = inferAssetRoot(sourceUrdfAbsolute);
  const urdfText = await fsPromises.readFile(sourceUrdfAbsolute, 'utf8');
  const robot = parseURDF(urdfText);
  if (!robot) {
    fail(`Failed to parse URDF: ${sourceUrdfAbsolute}`);
  }

  const payload = await exportRobotToUsd({
    robot,
    exportName: robot.name || path.basename(sourceUrdfAbsolute, path.extname(sourceUrdfAbsolute)),
    assets: await buildAssetMap(assetRootAbsolute),
    fileFormat: 'usda',
    layoutProfile: 'isaacsim',
    meshCompression: {
      enabled: true,
      quality: options.meshQuality,
    },
  });

  const { outputRoot, writtenFiles } = await writeExportedArchive(
    record,
    payload.archiveFiles,
    options.dryRun,
  );

  return {
    sourceUrdf: sourceUrdfAbsolute,
    outputUsda: path.resolve(record.output_usda),
    outputRoot,
    dryRun: options.dryRun,
    rootLayerPath: payload.rootLayerPath,
    archiveFileCount: payload.archiveFiles.size,
    writtenFiles: writtenFiles.map((entry) => normalizePath(path.relative(process.cwd(), entry))),
  };
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const records = await readManifest(options.manifestPath);
  const selectedRecords = selectRecords(records, options);

  if (selectedRecords.length === 0) {
    fail('No manifest records matched the provided filters.');
  }

  const originalWorker = globalThis.Worker;
  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: FakeColladaWorker,
  });

  try {
    const results = [];
    for (const record of selectedRecords) {
      results.push(await exportRecord(record, options));
    }
    process.stdout.write(`${JSON.stringify({ results }, null, 2)}\n`);
  } finally {
    disposeColladaParseWorkerPoolClient();
    disposeObjParseWorkerPoolClient();
    disposeStlParseWorkerPoolClient();
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
});

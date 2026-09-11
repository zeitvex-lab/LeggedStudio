import fs from 'node:fs/promises';
import path from 'node:path';
import { Buffer } from 'node:buffer';

import { JSDOM } from 'jsdom';

import { collectRobotAssetPaths } from '@/app/utils/import-preparation/criticalDeferredAssets';
import {
  disposeColladaParseWorkerPoolClient,
} from '@/core/loaders/colladaParseWorkerBridge';
import { parseColladaSceneData } from '@/core/loaders/colladaWorkerSceneData';
import { createLoadingManager, createMeshLoader } from '@/core/loaders/index';
import { parseStlGeometryData } from '@/core/loaders/stlGeometryData';
import { disposeStlParseWorkerPoolClient } from '@/core/loaders/stlParseWorkerBridge';
import { resolveRobotFileData, type RobotImportResult } from '@/core/parsers/importRobotFile';
import type { RobotFile } from '@/types';

type ValidationStatus = 'ready' | 'missing_entry' | 'import_error' | 'mesh_failed';

interface GazeboModelValidationSummary {
  model: string;
  entryPath: string | null;
  status: ValidationStatus;
  importStatus: RobotImportResult['status'] | null;
  importReason?: string | null;
  importMessage?: string | null;
  meshCount: number;
  loadedMeshCount: number;
  meshFailures: Array<{ meshPath: string; error: string }>;
  warnings: string[];
  errors: string[];
}

interface GazeboModelValidationReport {
  generatedAt: string;
  modelCount: number;
  readyCount: number;
  problemCount: number;
  warningCount: number;
  errorCount: number;
  summaries: GazeboModelValidationSummary[];
}

interface CliOptions {
  datasetRoot: string;
  outputPath: string;
  matches: string[];
  limit: number | null;
}

interface GazeboDatasetContext {
  absoluteFiles: string[];
  availableFiles: RobotFile[];
  allFileContents: Record<string, string>;
  assetMap: Record<string, string>;
  sourceFilesByModelDir: Map<string, string[]>;
}

const DEFAULT_DATASET_ROOT = path.resolve('test/gazebo_models');
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/gazebo-model-imports.json');
const TEXT_EXTENSIONS = new Set([
  '.config',
  '.dae',
  '.material',
  '.mdl',
  '.mtl',
  '.obj',
  '.sdf',
  '.txt',
  '.urdf',
  '.xml',
  '.xacro',
]);
const SOURCE_EXTENSIONS = new Set(['.mjcf', '.sdf', '.urdf', '.xml', '.xacro']);
const LOADABLE_MESH_EXTENSIONS = new Set(['.dae', '.glb', '.gltf', '.msh', '.obj', '.stl', '.vtk']);
const DEFAULT_MESH_LOAD_TIMEOUT_MS = 15_000;

function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, '/').replace(/^\/+/, '');
}

function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  globalThis.window = dom.window as typeof globalThis.window;
  globalThis.document = dom.window.document as typeof globalThis.document;
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
  globalThis.Node = dom.window.Node as typeof Node;
  globalThis.Element = dom.window.Element as typeof Element;
  globalThis.Document = dom.window.Document as typeof Document;
  globalThis.Image = dom.window.Image as typeof Image;
  globalThis.HTMLImageElement = dom.window.HTMLImageElement as typeof HTMLImageElement;
  globalThis.HTMLElement = dom.window.HTMLElement as typeof HTMLElement;
  globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;
  globalThis.self = globalThis;
}

class FakeMeshParseWorker {
  private readonly listeners = new Map<string, Set<(event: { data?: unknown }) => void>>();

  addEventListener(type: string, handler: (event: { data?: unknown }) => void): void {
    const handlers = this.listeners.get(type) ?? new Set<(event: { data?: unknown }) => void>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: (event: { data?: unknown }) => void): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown): void {
    void this.handleMessage(message);
  }

  terminate(): void {}

  private emit(type: 'message', event: { data: unknown }): void {
    this.listeners.get(type)?.forEach((handler) => {
      handler(event);
    });
  }

  private async handleMessage(message: unknown): Promise<void> {
    const request = message as { type?: string; requestId?: number; assetUrl?: string };
    if (typeof request.requestId !== 'number' || !request.assetUrl) {
      return;
    }

    try {
      const response = await fetch(request.assetUrl);
      if (!response.ok) {
        throw new Error(`Failed to fetch fake mesh asset: ${response.status} ${response.statusText}`);
      }

      if (request.type === 'parse-collada') {
        const colladaText = await response.text();
        const result = parseColladaSceneData(colladaText, request.assetUrl);
        this.emit('message', {
          data: {
            type: 'parse-collada-result',
            requestId: request.requestId,
            result,
          },
        });
        return;
      }

      if (request.type === 'parse-stl') {
        const result = parseStlGeometryData(await response.arrayBuffer());
        this.emit('message', {
          data: {
            type: 'parse-stl-result',
            requestId: request.requestId,
            result,
          },
        });
      }
    } catch (error) {
      if (request.type !== 'parse-collada' && request.type !== 'parse-stl') {
        return;
      }

      this.emit('message', {
        data: {
          type: `${request.type}-error`,
          requestId: request.requestId,
          error: error instanceof Error ? error.message : String(error),
        },
      });
    }
  }
}

function installFakeMeshWorker(): void {
  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: FakeMeshParseWorker as unknown as typeof Worker,
  });
  disposeColladaParseWorkerPoolClient();
  disposeStlParseWorkerPoolClient();
}

function parseCliArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    datasetRoot: DEFAULT_DATASET_ROOT,
    outputPath: DEFAULT_OUTPUT_PATH,
    matches: [],
    limit: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) {
        throw new Error(`Missing value for ${arg}`);
      }
      index += 1;
      return value;
    };

    switch (arg) {
      case '--dataset-root':
        options.datasetRoot = path.resolve(nextValue());
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--match':
        options.matches.push(nextValue().trim().toLowerCase());
        break;
      case '--limit': {
        const parsed = Number.parseInt(nextValue(), 10);
        if (!Number.isFinite(parsed) || parsed <= 0) {
          throw new Error(`Invalid --limit value: ${parsed}`);
        }
        options.limit = parsed;
        break;
      }
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function collectFiles(rootDir: string): Promise<string[]> {
  const files: string[] = [];

  async function visit(currentDir: string) {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.name.startsWith('.')) {
        continue;
      }

      const absolutePath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
      } else if (entry.isFile()) {
        files.push(absolutePath);
      }
    }
  }

  await visit(rootDir);
  return files;
}

function choosePreferredEntry(datasetRoot: string, modelDirName: string, sourceFiles: string[]): string | null {
  const normalized = sourceFiles.map((filePath) => normalizePath(path.relative(datasetRoot, filePath)));
  const preferredCandidates = [
    `${modelDirName}/model.sdf`,
    `${modelDirName}/${modelDirName}.sdf`,
    `${modelDirName}/model.urdf`,
    `${modelDirName}/${modelDirName}.urdf`,
  ];

  for (const candidate of preferredCandidates) {
    if (normalized.includes(candidate)) {
      return candidate;
    }
  }

  return normalized[0] ?? null;
}

function detectSourceFormat(filePath: string): Extract<RobotFile['format'], 'mjcf' | 'sdf' | 'urdf' | 'xacro'> {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === '.sdf') {
    return 'sdf';
  }
  if (extension === '.xacro') {
    return 'xacro';
  }
  if (extension === '.mjcf') {
    return 'mjcf';
  }
  return 'urdf';
}

function mimeForFile(filePath: string): string {
  switch (path.extname(filePath).toLowerCase()) {
    case '.dae':
      return 'text/xml';
    case '.gltf':
      return 'model/gltf+json';
    case '.glb':
      return 'model/gltf-binary';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.mtl':
    case '.obj':
    case '.material':
      return 'text/plain';
    case '.png':
      return 'image/png';
    case '.sdf':
    case '.urdf':
    case '.xml':
    case '.xacro':
      return 'application/xml';
    case '.svg':
      return 'image/svg+xml';
    default:
      return 'application/octet-stream';
  }
}

async function loadMeshAsync(
  loadMesh: ReturnType<typeof createMeshLoader>,
  meshPath: string,
  manager: ReturnType<typeof createLoadingManager>,
): Promise<void> {
  await Promise.race([
    new Promise<void>((resolve, reject) => {
      loadMesh(meshPath, manager, (_result, err) => {
        if (err) {
          reject(err);
          return;
        }

        resolve();
      });
    }),
    new Promise<void>((_, reject) => {
      setTimeout(() => {
        reject(new Error(`Timed out waiting for mesh loader callback after ${DEFAULT_MESH_LOAD_TIMEOUT_MS} ms.`));
      }, DEFAULT_MESH_LOAD_TIMEOUT_MS);
    }),
  ]);
}

async function createDatasetContext(datasetRoot: string): Promise<GazeboDatasetContext> {
  const absoluteFiles = await collectFiles(datasetRoot);
  const availableFiles: RobotFile[] = [];
  const allFileContents: Record<string, string> = {};
  const assetMap: Record<string, string> = {};
  const sourceFilesByModelDir = new Map<string, string[]>();

  for (const absolutePath of absoluteFiles) {
    const datasetRelativePath = normalizePath(path.relative(datasetRoot, absolutePath));
    const [modelDirName] = datasetRelativePath.split('/');
    const extension = path.extname(absolutePath).toLowerCase();
    let textContent: string | null = null;

    if (TEXT_EXTENSIONS.has(extension)) {
      textContent = await fs.readFile(absolutePath, 'utf8');
      allFileContents[datasetRelativePath] = textContent;
    }

    if (SOURCE_EXTENSIONS.has(extension)) {
      const sourceFiles = sourceFilesByModelDir.get(modelDirName) ?? [];
      sourceFiles.push(datasetRelativePath);
      sourceFilesByModelDir.set(modelDirName, sourceFiles);
      availableFiles.push({
        name: datasetRelativePath,
        format: detectSourceFormat(absolutePath),
        content: textContent ?? (await fs.readFile(absolutePath, 'utf8')),
      });
    }

    const data = await fs.readFile(absolutePath);
    const dataUrl = `data:${mimeForFile(absolutePath)};base64,${Buffer.from(data).toString('base64')}`;
    assetMap[datasetRelativePath] = dataUrl;
  }

  return {
    absoluteFiles,
    availableFiles,
    allFileContents,
    assetMap,
    sourceFilesByModelDir,
  };
}

function createImportErrorSummary(options: {
  model: string;
  entryPath: string | null;
  importResult: Exclude<RobotImportResult, { status: 'ready' }>;
  warnings: string[];
  errors: string[];
}): GazeboModelValidationSummary {
  return {
    model: options.model,
    entryPath: options.entryPath,
    status: options.entryPath ? 'import_error' : 'missing_entry',
    importStatus: options.importResult.status,
    importReason: options.importResult.status === 'error' ? options.importResult.reason : null,
    importMessage: options.importResult.status === 'error' ? options.importResult.message ?? null : null,
    meshCount: 0,
    loadedMeshCount: 0,
    meshFailures: [],
    warnings: options.warnings,
    errors: options.errors,
  };
}

async function validateModel(
  datasetRoot: string,
  datasetContext: GazeboDatasetContext,
  modelDirName: string,
): Promise<GazeboModelValidationSummary> {
  const sourceFiles =
    datasetContext.sourceFilesByModelDir.get(modelDirName)?.map((filePath) =>
      path.join(datasetRoot, filePath),
    ) ?? [];
  const entryPath = choosePreferredEntry(datasetRoot, modelDirName, sourceFiles);
  const warnings: string[] = [];
  const errors: string[] = [];
  const originalWarn = console.warn;
  const originalError = console.error;
  const originalDebug = console.debug;
  const originalLog = console.log;

  console.warn = (...args: unknown[]) => {
    warnings.push(args.map((arg) => String(arg)).join(' '));
  };
  console.error = (...args: unknown[]) => {
    errors.push(args.map((arg) => String(arg)).join(' '));
  };
  console.debug = () => {};
  console.log = () => {};

  try {
    if (!entryPath) {
      return {
        model: modelDirName,
        entryPath: null,
        status: 'missing_entry',
        importStatus: null,
        importReason: null,
        importMessage: null,
        meshCount: 0,
        loadedMeshCount: 0,
        meshFailures: [],
        warnings,
        errors,
      };
    }

    const sourceFile = datasetContext.availableFiles.find((file) => file.name === entryPath) ?? null;
    if (!sourceFile) {
      return {
        model: modelDirName,
        entryPath,
        status: 'missing_entry',
        importStatus: null,
        importReason: null,
        importMessage: `Preferred entry missing from available files: ${entryPath}`,
        meshCount: 0,
        loadedMeshCount: 0,
        meshFailures: [],
        warnings,
        errors,
      };
    }

    const importResult = resolveRobotFileData(sourceFile, {
      availableFiles: datasetContext.availableFiles,
      allFileContents: datasetContext.allFileContents,
    });

    if (importResult.status !== 'ready') {
      return createImportErrorSummary({
        model: modelDirName,
        entryPath,
        importResult,
        warnings,
        errors,
      });
    }

    const meshPaths = [...collectRobotAssetPaths(importResult.robotData)]
      .filter((assetPath) => LOADABLE_MESH_EXTENSIONS.has(path.extname(String(assetPath)).toLowerCase()))
      .sort();
    const manager = createLoadingManager(datasetContext.assetMap, path.posix.dirname(entryPath));
    const loadMesh = createMeshLoader(
      datasetContext.assetMap,
      manager,
      path.posix.dirname(entryPath),
    );
    const meshFailures: Array<{ meshPath: string; error: string }> = [];
    let loadedMeshCount = 0;

    for (const meshPath of meshPaths) {
      try {
        await loadMeshAsync(loadMesh, meshPath, manager);
        loadedMeshCount += 1;
      } catch (error) {
        meshFailures.push({
          meshPath,
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }

    return {
      model: modelDirName,
      entryPath,
      status: meshFailures.length === 0 ? 'ready' : 'mesh_failed',
      importStatus: importResult.status,
      importReason: null,
      importMessage: null,
      meshCount: meshPaths.length,
      loadedMeshCount,
      meshFailures,
      warnings,
      errors,
    };
  } finally {
    console.warn = originalWarn;
    console.error = originalError;
    console.debug = originalDebug;
    console.log = originalLog;
  }
}

async function main(): Promise<void> {
  const options = parseCliArgs(process.argv.slice(2));
  installDomGlobals();
  installFakeMeshWorker();
  const datasetContext = await createDatasetContext(options.datasetRoot);

  const requestedModelDirs = (await fs.readdir(options.datasetRoot, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.'))
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right));
  const modelDirs = requestedModelDirs.filter((modelDirName) => {
    if (options.matches.length === 0) {
      return true;
    }

    const haystack = modelDirName.toLowerCase();
    return options.matches.every((filter) => haystack.includes(filter));
  });
  const limitedModelDirs =
    options.limit == null ? modelDirs : modelDirs.slice(0, options.limit);

  const summaries: GazeboModelValidationSummary[] = [];
  for (const modelDirName of limitedModelDirs) {
    summaries.push(await validateModel(options.datasetRoot, datasetContext, modelDirName));
  }

  const report: GazeboModelValidationReport = {
    generatedAt: new Date().toISOString(),
    modelCount: summaries.length,
    readyCount: summaries.filter((summary) => summary.status === 'ready').length,
    problemCount: summaries.filter((summary) => summary.status !== 'ready').length,
    warningCount: summaries.reduce((sum, summary) => sum + summary.warnings.length, 0),
    errorCount: summaries.reduce((sum, summary) => sum + summary.errors.length, 0),
    summaries,
  };

  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
  await fs.writeFile(options.outputPath, JSON.stringify(report, null, 2));

  console.log(JSON.stringify(report, null, 2));
}

try {
  await main();
} catch (error) {
  console.error(error instanceof Error ? error.stack || error.message : String(error));
  process.exitCode = 1;
}

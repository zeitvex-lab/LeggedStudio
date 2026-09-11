import fsPromises from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import process from 'node:process';

import { JSDOM } from 'jsdom';

import { detectImportFormat } from '../../../src/app/utils/importPreparation.ts';
import { disposeColladaParseWorkerPoolClient } from '../../../src/core/loaders/colladaParseWorkerBridge.ts';
import { disposeObjParseWorkerPoolClient } from '../../../src/core/loaders/objParseWorkerBridge.ts';
import { disposeStlParseWorkerPoolClient } from '../../../src/core/loaders/stlParseWorkerBridge.ts';
import { resolveRobotFileData } from '../../../src/core/parsers/importRobotFile.ts';
import { exportRobotToUsd } from '../../../src/features/file-io/utils/usdExport.ts';
import type { RobotData, RobotFile } from '../../../src/types';

const DEFAULT_FIXTURE_ROOT = path.resolve('test/mujoco_menagerie-main');
const DEFAULT_ARTIFACT_ROOT = path.resolve('tmp/regression/mujoco-usd-export-performance');
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/mujoco-usd-export-performance-summary.json');
const DEFAULT_MODEL_PATHS = [
  'agilex_piper/piper.xml',
  'franka_emika_panda/panda.xml',
  'robotiq_2f85/2f85.xml',
  'trossen_vx300s/vx300s.xml',
  'unitree_go2/go2.xml',
];

type UsdExportFileFormat = 'usd' | 'usda';

type Options = {
  artifactsDir: string;
  compressMeshes: boolean;
  fileFormat: UsdExportFileFormat;
  fixtureRoot: string;
  limit: number | null;
  meshQuality: number;
  modelFilters: string[];
  outputPath: string;
  writeArchives: boolean;
};

type SourceContext = {
  allFileContents: Record<string, string>;
  assets: Record<string, string>;
  availableFiles: RobotFile[];
};

type ModelFixture = {
  entryAbsPath: string;
  entryPath: string;
  id: string;
  packageName: string;
  supportRootAbs: string;
  supportRootRel: string;
};

type PhaseTimes = Record<string, number>;

type UsdLayerMetrics = {
  baseLayerBytes: number;
  geomSubsetCount: number;
  materialBindingCount: number;
  materialPrimCount: number;
  meshPrimCount: number;
  nestedChildPrimCount: number;
  textureAssetCount: number;
  visualMergedCount: number;
  xformPrimCount: number;
};

type FixtureResult = {
  archiveFileCount: number;
  entryPath: string;
  exportMs: number;
  exportName: string;
  failures: string[];
  id: string;
  importMs: number;
  linkCount: number;
  loadSupportFilesMs: number;
  metrics: UsdLayerMetrics | null;
  packageName: string;
  pass: boolean;
  phaseMs: PhaseTimes;
  progressEventCount: number;
  rootLayerPath: string | null;
};

const TEXT_CONTENT_EXTENSIONS = new Set([
  '.config',
  '.dae',
  '.json',
  '.material',
  '.mdl',
  '.mjcf',
  '.mtl',
  '.obj',
  '.sdf',
  '.txt',
  '.urdf',
  '.usda',
  '.xacro',
  '.xml',
]);
const SOURCE_FILE_EXTENSIONS = new Set(['.mjcf', '.sdf', '.urdf', '.xacro', '.xml']);
const MESH_FILE_EXTENSIONS = new Set(['.dae', '.glb', '.gltf', '.msh', '.obj', '.stl']);
const ASSET_EXTENSIONS = new Set([
  '.bmp',
  '.dae',
  '.gif',
  '.glb',
  '.gltf',
  '.jpeg',
  '.jpg',
  '.msh',
  '.mtl',
  '.obj',
  '.png',
  '.stl',
  '.svg',
  '.webp',
]);
const IMAGE_EXTENSIONS = new Set(['.bmp', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp']);
const EXCLUDED_FIXTURE_DIR_NAMES = new Set(['.github', 'assets', 'test']);

function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
  if (typeof globalThis.ProgressEvent === 'undefined') {
    globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;
  }

  delete (globalThis as typeof globalThis & { Worker?: typeof Worker }).Worker;
}

function fail(message: string): never {
  throw new Error(message);
}

function normalizePathSlashes(filePath: string): string {
  return filePath.replace(/\\/g, '/');
}

function sanitizeIdentifier(value: string): string {
  return value.replace(/[^a-z0-9._-]+/gi, '_').replace(/^_+|_+$/g, '') || 'robot';
}

function parseInteger(value: string, flagName: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    fail(`Invalid value for ${flagName}: ${value}`);
  }
  return parsed;
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    artifactsDir: DEFAULT_ARTIFACT_ROOT,
    compressMeshes: false,
    fileFormat: 'usd',
    fixtureRoot: DEFAULT_FIXTURE_ROOT,
    limit: null,
    meshQuality: 100,
    modelFilters: [],
    outputPath: DEFAULT_OUTPUT_PATH,
    writeArchives: false,
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
      case '--artifact-dir':
      case '--artifacts-dir':
        options.artifactsDir = path.resolve(nextValue());
        break;
      case '--compress-meshes':
        options.compressMeshes = true;
        break;
      case '--file-format': {
        const value = nextValue();
        if (value !== 'usd' && value !== 'usda') {
          fail(`Invalid value for --file-format: ${value}`);
        }
        options.fileFormat = value;
        break;
      }
      case '--fixture-root':
        options.fixtureRoot = path.resolve(nextValue());
        break;
      case '--limit':
        options.limit = parseInteger(nextValue(), '--limit');
        break;
      case '--mesh-quality':
        options.meshQuality = parseInteger(nextValue(), '--mesh-quality');
        break;
      case '--model':
        options.modelFilters.push(nextValue().toLowerCase());
        break;
      case '--output':
        options.outputPath = path.resolve(nextValue());
        break;
      case '--write-archives':
        options.writeArchives = true;
        break;
      case '--help':
      case '-h':
        process.stdout.write(`Usage:
  npx tsx scripts/test/benchmark/benchmark_mujoco_usd_export.ts [options]

Options:
  --fixture-root <path>    MuJoCo menagerie root. Default: ${DEFAULT_FIXTURE_ROOT}
  --output <path>          Summary JSON path. Default: ${DEFAULT_OUTPUT_PATH}
  --artifacts-dir <path>   Archive output root when --write-archives is used.
  --model <filter>         Restrict to matching MJCF source path/id. Repeatable.
  --limit <count>          Limit selected models.
  --file-format <usd|usda> USD layer extension. Default: usd
  --compress-meshes        Enable mesh compression during export.
  --mesh-quality <count>   Compression quality. Default: 100
  --write-archives         Write exported archive files under artifacts dir.
  --help                   Show this help.
`);
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

async function pathExists(filePath: string): Promise<boolean> {
  try {
    await fsPromises.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function collectFiles(rootDir: string): Promise<string[]> {
  const entries = await fsPromises.readdir(rootDir, { withFileTypes: true });
  const results: string[] = [];

  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await collectFiles(absolutePath)));
      continue;
    }
    if (entry.isFile()) {
      results.push(absolutePath);
    }
  }

  return results;
}

async function collectSupportRoots(rootDir: string): Promise<string[]> {
  const entries = await fsPromises.readdir(rootDir, { withFileTypes: true });
  return entries
    .filter(
      (entry) =>
        entry.isDirectory() &&
        !EXCLUDED_FIXTURE_DIR_NAMES.has(entry.name) &&
        !entry.name.startsWith('.'),
    )
    .map((entry) => path.join(rootDir, entry.name))
    .sort((left, right) => left.localeCompare(right));
}

function guessMimeType(filePath: string): string {
  switch (path.extname(filePath).toLowerCase()) {
    case '.dae':
      return 'model/vnd.collada+xml';
    case '.gif':
      return 'image/gif';
    case '.glb':
      return 'model/gltf-binary';
    case '.gltf':
      return 'model/gltf+json';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.mtl':
    case '.obj':
      return 'text/plain';
    case '.png':
      return 'image/png';
    case '.stl':
      return 'model/stl';
    case '.svg':
      return 'image/svg+xml';
    case '.webp':
      return 'image/webp';
    default:
      return 'application/octet-stream';
  }
}

function createDataUrl(filePath: string, buffer: Buffer): string {
  return `data:${guessMimeType(filePath)};base64,${buffer.toString('base64')}`;
}

async function createSourceContext(
  fixtureRoot: string,
  supportRootAbs: string,
): Promise<SourceContext> {
  const roots = [supportRootAbs];
  const sharedAssetsRoot = path.join(fixtureRoot, 'assets');
  if (sharedAssetsRoot !== supportRootAbs && (await pathExists(sharedAssetsRoot))) {
    roots.push(sharedAssetsRoot);
  }

  const availableFiles = new Map<string, RobotFile>();
  const allFileContents: Record<string, string> = {};
  const assets: Record<string, string> = {};

  for (const rootAbs of roots) {
    for (const absolutePath of await collectFiles(rootAbs)) {
      const datasetRelativePath = normalizePathSlashes(path.relative(fixtureRoot, absolutePath));
      const extension = path.extname(absolutePath).toLowerCase();

      if (TEXT_CONTENT_EXTENSIONS.has(extension)) {
        const content = await fsPromises.readFile(absolutePath, 'utf8');
        allFileContents[datasetRelativePath] = content;

        if (SOURCE_FILE_EXTENSIONS.has(extension)) {
          const format = detectImportFormat(content, datasetRelativePath);
          if (format) {
            availableFiles.set(datasetRelativePath, {
              name: datasetRelativePath,
              content,
              format,
            });
          }
        }
      }

      if (MESH_FILE_EXTENSIONS.has(extension) && !availableFiles.has(datasetRelativePath)) {
        availableFiles.set(datasetRelativePath, {
          name: datasetRelativePath,
          content: '',
          format: 'mesh',
        });
      }

      if (IMAGE_EXTENSIONS.has(extension)) {
        const buffer = await fsPromises.readFile(absolutePath);
        assets[datasetRelativePath] = createDataUrl(absolutePath, buffer);
      }
    }
  }

  return {
    allFileContents,
    assets,
    availableFiles: Array.from(availableFiles.values()).sort((left, right) =>
      left.name.localeCompare(right.name),
    ),
  };
}

function createFixtureId(supportRootRel: string, entryPath: string): string {
  const packageName = path.basename(supportRootRel);
  const stem = path.basename(entryPath, path.extname(entryPath));
  return stem === packageName ? supportRootRel : `${supportRootRel}/${stem}`;
}

function matchesSelectedModel(options: Options, fixture: ModelFixture): boolean {
  const defaultSelected =
    options.modelFilters.length === 0 && DEFAULT_MODEL_PATHS.includes(fixture.entryPath);
  if (defaultSelected) {
    return true;
  }

  const haystack = `${fixture.id} ${fixture.packageName} ${fixture.entryPath}`.toLowerCase();
  return options.modelFilters.some((filter) => haystack.includes(filter));
}

async function discoverFixtures(options: Options): Promise<ModelFixture[]> {
  const fixtures: ModelFixture[] = [];

  for (const supportRootAbs of await collectSupportRoots(options.fixtureRoot)) {
    const supportRootRel = normalizePathSlashes(path.relative(options.fixtureRoot, supportRootAbs));
    const packageName = path.basename(supportRootAbs);
    const context = await createSourceContext(options.fixtureRoot, supportRootAbs);

    context.availableFiles.forEach((file) => {
      if (file.format !== 'mjcf') {
        return;
      }

      fixtures.push({
        entryAbsPath: path.join(options.fixtureRoot, file.name),
        entryPath: file.name,
        id: createFixtureId(supportRootRel, file.name),
        packageName,
        supportRootAbs,
        supportRootRel,
      });
    });
  }

  const selected = fixtures
    .filter((fixture) => matchesSelectedModel(options, fixture))
    .sort((left, right) => {
      const leftDefaultIndex = DEFAULT_MODEL_PATHS.indexOf(left.entryPath);
      const rightDefaultIndex = DEFAULT_MODEL_PATHS.indexOf(right.entryPath);
      if (leftDefaultIndex !== -1 || rightDefaultIndex !== -1) {
        return (leftDefaultIndex === -1 ? Number.MAX_SAFE_INTEGER : leftDefaultIndex) -
          (rightDefaultIndex === -1 ? Number.MAX_SAFE_INTEGER : rightDefaultIndex);
      }
      return left.entryPath.localeCompare(right.entryPath);
    });

  if (selected.length === 0) {
    fail('No MuJoCo MJCF fixtures matched the selected filters.');
  }

  return options.limit === null ? selected : selected.slice(0, options.limit);
}

async function collectAssetFiles(rootDir: string, baseDir = rootDir): Promise<string[]> {
  const entries = await fsPromises.readdir(rootDir, { withFileTypes: true });
  const results: string[] = [];

  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...(await collectAssetFiles(absolutePath, baseDir)));
      continue;
    }

    if (!entry.isFile() || !ASSET_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      continue;
    }

    results.push(path.relative(baseDir, absolutePath).split(path.sep).join('/'));
  }

  return results;
}

async function buildExtraAssetFiles(
  fixtureRoot: string,
  fixture: ModelFixture,
): Promise<Map<string, Blob>> {
  const extraMeshFiles = new Map<string, Blob>();
  const assetRoots = [fixture.supportRootAbs];
  const sharedAssetsRoot = path.join(fixtureRoot, 'assets');
  if (sharedAssetsRoot !== fixture.supportRootAbs && (await pathExists(sharedAssetsRoot))) {
    assetRoots.push(sharedAssetsRoot);
  }

  for (const assetRoot of assetRoots) {
    const packageName = path.basename(assetRoot);
    const assetFiles = await collectAssetFiles(assetRoot);

    for (const relativePath of assetFiles) {
      const absolutePath = path.join(assetRoot, relativePath);
      const datasetRelativePath = normalizePathSlashes(path.relative(fixtureRoot, absolutePath));
      const entryRelativePath = path.posix.relative(
        path.posix.dirname(fixture.entryPath),
        datasetRelativePath,
      );
      const blob = new Blob([await fsPromises.readFile(absolutePath)], {
        type: guessMimeType(absolutePath),
      });
      const aliases = [
        relativePath,
        datasetRelativePath,
        entryRelativePath,
        `${packageName}/${relativePath}`,
        `package://${packageName}/${relativePath}`,
      ];

      aliases.forEach((alias) => {
        if (alias && alias !== '.' && !extraMeshFiles.has(alias)) {
          extraMeshFiles.set(alias, blob);
        }
      });
    }
  }

  return extraMeshFiles;
}

function countMatches(value: string, pattern: RegExp): number {
  return Array.from(value.matchAll(pattern)).length;
}

async function readArchiveText(archiveFiles: Map<string, Blob>, archivePath: string): Promise<string> {
  const blob = archiveFiles.get(archivePath);
  if (!blob) {
    throw new Error(`Archive entry missing: ${archivePath}`);
  }
  return Buffer.from(await blob.arrayBuffer()).toString('utf8');
}

function findBaseLayerPath(archiveFiles: Map<string, Blob>): string | null {
  return (
    Array.from(archiveFiles.keys()).find((archivePath) =>
      /\/configuration\/[^/]+_base\.(?:usd|usda)$/i.test(archivePath),
    ) ?? null
  );
}

function collectUsdLayerMetrics(
  baseLayer: string,
  archiveFiles: Map<string, Blob>,
): UsdLayerMetrics {
  const textureAssetCount = Array.from(archiveFiles.keys()).filter((archivePath) => {
    return /\/usd\/assets\/.+\.(?:bmp|gif|jpe?g|png|svg|webp)$/i.test(archivePath);
  }).length;

  return {
    baseLayerBytes: Buffer.byteLength(baseLayer),
    geomSubsetCount: countMatches(baseLayer, /\bdef GeomSubset "/g),
    materialBindingCount: countMatches(baseLayer, /\brel material:binding/g),
    materialPrimCount: countMatches(baseLayer, /\bdef Material "/g),
    meshPrimCount: countMatches(baseLayer, /\bdef Mesh "/g),
    nestedChildPrimCount: countMatches(baseLayer, /_child_\d+/g),
    textureAssetCount,
    visualMergedCount: countMatches(baseLayer, /\bdef Mesh "visual_merged"/g),
    xformPrimCount: countMatches(baseLayer, /\bdef Xform "/g),
  };
}

function validateExport(
  fixture: ModelFixture,
  robotData: RobotData,
  metrics: UsdLayerMetrics | null,
  archiveFileCount: number,
  progressEventCount: number,
  phaseMs: PhaseTimes,
  baseLayer: string | null,
): string[] {
  const failures: string[] = [];
  const linkCount = Object.keys(robotData.links ?? {}).length;
  const jointCount = Object.keys(robotData.joints ?? {}).length;

  if (linkCount <= 0) {
    failures.push('import produced no links');
  }
  if (archiveFileCount <= 0) {
    failures.push('USD archive is empty');
  }
  if (progressEventCount <= 0) {
    failures.push('export did not report progress events');
  }
  if (!Number.isFinite(phaseMs.scene)) {
    failures.push('missing USD scene phase timing');
  }
  if (!metrics || !baseLayer) {
    failures.push('missing USD base layer');
    return failures;
  }
  if (metrics.baseLayerBytes <= 0) {
    failures.push('USD base layer is empty');
  }
  if (metrics.meshPrimCount <= 0) {
    failures.push('USD base layer contains no mesh prims');
  }
  if (metrics.materialBindingCount <= 0) {
    failures.push('USD base layer contains no material bindings');
  }
  if (!baseLayer.includes('color3f inputs:diffuseColor')) {
    failures.push('USD base layer contains no preview diffuse colors');
  }

  if (fixture.entryPath === 'agilex_piper/piper.xml') {
    if (!/(?:custom string urdf:linkId = "link7"|def Xform "link7")/.test(baseLayer)) {
      failures.push('Piper link7 prim is missing from the USD base layer');
    }
    if (metrics.visualMergedCount < 4) {
      failures.push(
        `Piper same-link visual merge count is too low: ${metrics.visualMergedCount}`,
      );
    }
    if (metrics.geomSubsetCount < metrics.visualMergedCount) {
      failures.push('Piper merged visuals did not retain material GeomSubsets');
    }
    if (/child_0_child_0/.test(baseLayer)) {
      failures.push('Piper export still contains deeply nested child_0_child_0 visual prims');
    }
  }

  if (fixture.entryPath === 'trossen_vx300s/vx300s.xml') {
    if (metrics.textureAssetCount <= 0) {
      failures.push('VX300s textured logo asset was not exported');
    }
    if (!baseLayer.includes('interbotix_black')) {
      failures.push('VX300s Interbotix material/texture name is missing from USD');
    }
  }

  if (jointCount <= 0 && !fixture.entryPath.includes('robotiq')) {
    failures.push('import produced no joints');
  }

  return failures;
}

async function writeArchiveFiles(rootDir: string, archiveFiles: Map<string, Blob>): Promise<void> {
  for (const [archivePath, blob] of archiveFiles.entries()) {
    const absolutePath = path.join(rootDir, archivePath);
    await fsPromises.mkdir(path.dirname(absolutePath), { recursive: true });
    await fsPromises.writeFile(absolutePath, Buffer.from(await blob.arrayBuffer()));
  }
}

async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  await fsPromises.mkdir(path.dirname(filePath), { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await fsPromises.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  await fsPromises.rename(tempPath, filePath);
}

async function benchmarkFixture(options: Options, fixture: ModelFixture): Promise<FixtureResult> {
  const loadSupportStart = performance.now();
  const sourceContext = await createSourceContext(options.fixtureRoot, fixture.supportRootAbs);
  const extraMeshFiles = await buildExtraAssetFiles(options.fixtureRoot, fixture);
  const sourceFile = sourceContext.availableFiles.find((file) => file.name === fixture.entryPath);
  const loadSupportFilesMs = Math.round(performance.now() - loadSupportStart);

  if (!sourceFile) {
    fail(`Source file not found in source context: ${fixture.entryPath}`);
  }

  const importStart = performance.now();
  const importResult = resolveRobotFileData(sourceFile, {
    allFileContents: sourceContext.allFileContents,
    assets: sourceContext.assets,
    availableFiles: sourceContext.availableFiles,
  });
  const importMs = Math.round(performance.now() - importStart);
  if (importResult.status !== 'ready') {
    const message = importResult.status === 'error' ? importResult.message : importResult.status;
    fail(`Import failed for ${fixture.entryPath}: ${message || 'unknown error'}`);
  }

  const robotData = importResult.robotData;
  const phaseStarts = new Map<string, number>();
  const phaseEnds = new Map<string, number>();
  const phaseLastSeen = new Map<string, number>();
  let progressEventCount = 0;
  const exportName = sanitizeIdentifier(`${fixture.supportRootRel}_${path.basename(fixture.entryPath, '.xml')}`);
  const exportStart = performance.now();
  const payload = await exportRobotToUsd({
    robot: robotData,
    exportName,
    assets: sourceContext.assets,
    extraMeshFiles,
    fileFormat: options.fileFormat,
    ...(options.compressMeshes
      ? {
          meshCompression: {
            enabled: true,
            quality: options.meshQuality,
          },
        }
      : {}),
    onProgress: (progress) => {
      const now = performance.now();
      const phase = String(progress.phase || '');
      if (!phase) {
        return;
      }

      if (!phaseStarts.has(phase)) {
        phaseStarts.set(phase, now);
      }
      phaseLastSeen.set(phase, now);
      progressEventCount += 1;

      if (Number(progress.total) > 0 && Number(progress.completed) >= Number(progress.total)) {
        phaseEnds.set(phase, now);
      }
    },
  });
  const exportMs = Math.round(performance.now() - exportStart);

  const phaseMs: PhaseTimes = {};
  ['links', 'geometry', 'scene', 'assets'].forEach((phase) => {
    const started = phaseStarts.get(phase);
    if (started == null) {
      return;
    }
    const stopped = phaseEnds.get(phase) ?? phaseLastSeen.get(phase) ?? performance.now();
    phaseMs[phase] = Math.round(stopped - started);
  });

  const baseLayerPath = findBaseLayerPath(payload.archiveFiles);
  const baseLayer = baseLayerPath ? await readArchiveText(payload.archiveFiles, baseLayerPath) : null;
  const metrics = baseLayer ? collectUsdLayerMetrics(baseLayer, payload.archiveFiles) : null;
  const failures = validateExport(
    fixture,
    robotData,
    metrics,
    payload.archiveFiles.size,
    progressEventCount,
    phaseMs,
    baseLayer,
  );

  if (options.writeArchives) {
    await writeArchiveFiles(path.join(options.artifactsDir, fixture.id), payload.archiveFiles);
  }

  return {
    archiveFileCount: payload.archiveFiles.size,
    entryPath: fixture.entryPath,
    exportMs,
    exportName,
    failures,
    id: fixture.id,
    importMs,
    linkCount: Object.keys(robotData.links ?? {}).length,
    loadSupportFilesMs,
    metrics,
    packageName: fixture.packageName,
    pass: failures.length === 0,
    phaseMs,
    progressEventCount,
    rootLayerPath: payload.rootLayerPath ?? null,
  };
}

async function main(): Promise<void> {
  installDomGlobals();
  const options = parseArgs(process.argv.slice(2));
  const fixtures = await discoverFixtures(options);
  const startedAt = new Date().toISOString();
  const results: FixtureResult[] = [];

  for (const fixture of fixtures) {
    process.stdout.write(`[mujoco-usd-export] ${fixture.entryPath}\n`);
    try {
      const result = await benchmarkFixture(options, fixture);
      results.push(result);
      const metrics = result.metrics;
      process.stdout.write(
        `  import=${result.importMs}ms export=${result.exportMs}ms meshes=${
          metrics?.meshPrimCount ?? 0
        } merged=${metrics?.visualMergedCount ?? 0} textures=${
          metrics?.textureAssetCount ?? 0
        } status=${result.pass ? 'pass' : 'fail'}\n`,
      );
      result.failures.forEach((failure) => process.stdout.write(`    - ${failure}\n`));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      results.push({
        archiveFileCount: 0,
        entryPath: fixture.entryPath,
        exportMs: 0,
        exportName: sanitizeIdentifier(fixture.id),
        failures: [message],
        id: fixture.id,
        importMs: 0,
        linkCount: 0,
        loadSupportFilesMs: 0,
        metrics: null,
        packageName: fixture.packageName,
        pass: false,
        phaseMs: {},
        progressEventCount: 0,
        rootLayerPath: null,
      });
      process.stdout.write(`  status=fail ${message}\n`);
    }
  }

  const failed = results.filter((result) => !result.pass);
  const summary = {
    artifactsDir: options.writeArchives ? options.artifactsDir : null,
    completedAt: new Date().toISOString(),
    failed: failed.length,
    fileFormat: options.fileFormat,
    fixtureRoot: options.fixtureRoot,
    modelCount: results.length,
    passed: results.length - failed.length,
    results,
    startedAt,
  };
  await writeJsonAtomic(options.outputPath, summary);
  process.stdout.write(`[mujoco-usd-export] summary=${options.outputPath}\n`);

  if (failed.length > 0) {
    throw new Error(`${failed.length} MuJoCo USD export fixture(s) failed validation.`);
  }
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  })
  .finally(() => {
    disposeColladaParseWorkerPoolClient();
    disposeObjParseWorkerPoolClient();
    disposeStlParseWorkerPoolClient();
  });

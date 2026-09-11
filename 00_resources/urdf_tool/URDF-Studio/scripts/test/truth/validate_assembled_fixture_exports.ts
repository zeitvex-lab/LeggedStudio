import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';

import {
  buildFixtureMatrix,
  DATASET_NAMES,
  installDomGlobals,
  type DatasetName,
  type FixtureSummary,
} from './importFixtureMatrixShared';
import {
  buildExportableAssemblyRobotData,
} from '@/core/robot/assemblyTransforms';
import { prepareAssemblyRobotData } from '@/core/robot/assemblyComponentPreparation';
import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { generateURDF } from '@/core/parsers/urdf/urdfGenerator';
import { generateMujocoXML } from '@/core/parsers/mjcf/mjcfGenerator';
import { detectImportFormat } from '@/app/utils/import-preparation/formatDetection';
import { exportRobotToUsd } from '@/features/file-io/utils/usdExportCoordinator';
import { buildAssemblyComponentIdentity } from '@/core/robot/assemblyComponentPreparation';
import { DEFAULT_JOINT, JointType } from '@/types';
import type {
  AssemblyComponent,
  AssemblyState,
  BridgeJoint,
  RobotData,
  RobotFile,
} from '@/types';

const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/assembled-test-exports-summary.json');
const DEFAULT_ARTIFACT_DIR = path.resolve('tmp/regression/assembled-test-exports');
const DEFAULT_GROUP_SIZE = 2;
const DEFAULT_ISAAC_PYTHON = path.resolve('/home/xiangyk/anaconda3/envs/isaaclab22/bin/python');
const DEFAULT_ISAACLAB_ROOT = path.resolve(
  '/home/xiangyk/Project/IsaacLab_Family/IsaacLab22/IsaacLab',
);
const DEFAULT_MUJOCO_PYTHON = path.resolve('/home/xiangyk/anaconda3/envs/isaaclab22/bin/python');
const DEFAULT_COLOR_TOLERANCE = 0.002;
const DEFAULT_MESH_QUALITY = 75;
const unhandledRejectionRecords: string[] = [];

process.on('unhandledRejection', (reason: unknown) => {
  if (typeof reason === 'string') {
    unhandledRejectionRecords.push(reason);
    return;
  }
  if (reason instanceof Error) {
    unhandledRejectionRecords.push(`${reason.name}: ${reason.message}`);
    return;
  }
  try {
    unhandledRejectionRecords.push(JSON.stringify(reason));
  } catch {
    unhandledRejectionRecords.push(String(reason));
  }
});

const TEXT_CONTENT_EXTENSIONS = new Set([
  '.config',
  '.json',
  '.material',
  '.mdl',
  '.mjcf',
  '.mtl',
  '.sdf',
  '.txt',
  '.urdf',
  '.usda',
  '.xacro',
  '.xml',
]);

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
  '.msh',
]);

function recordUnhandledRejectionFailures(
  phase: string,
  report: GroupReport,
  stageFailures: string[] | null = null,
): void {
  const records = drainUnhandledRejections();
  if (records.length === 0) {
    return;
  }
  const failures = [...new Set(records)].map((message) => `Unhandled rejection in ${phase}: ${message}`);
  report.failures.push(...failures);
  if (stageFailures) {
    stageFailures.push(...failures);
  }
  report.status = report.status === 'fail' ? 'fail' : 'partial';
}

function drainUnhandledRejections(): string[] {
  if (unhandledRejectionRecords.length === 0) {
    return [];
  }
  const drained = [...unhandledRejectionRecords];
  unhandledRejectionRecords.length = 0;
  return drained;
}

async function yieldToEventLoop(): Promise<void> {
  await new Promise<void>((resolve) => {
    setTimeout(() => resolve(), 0);
  });
}

type ExecutionOptions = {
  outputPath: string;
  artifactsDir: string;
  datasets: DatasetName[];
  matches: string[];
  limit: number | null;
  groupSize: number;
  skipIsaacCheck: boolean;
  skipMujocoCheck: boolean;
  isaacPython: string;
  isaacLabRoot: string;
  mujocoPython: string;
};

type PreparedFixture = {
  summary: FixtureSummary;
  file: RobotFile;
  robotData: RobotData;
  context: SourceContext;
  componentIdentity: {
    componentId: string;
    componentName: string;
  };
};

type FixtureImportResult =
  | { kind: 'ok'; file: RobotFile; robotData: RobotData }
  | { kind: 'error'; message: string };

type ParsedMaterialSignature = {
  color: [number, number, number] | null;
  textured: boolean;
};

type GroupReport = {
  groupId: string;
  sourceEntries: string[];
  sourceDatasets: string[];
  status: 'pass' | 'fail' | 'partial';
  failures: string[];
  urdf: {
    path: string | null;
    exportedLength: number | null;
    parsePassed: boolean;
    parseMessage: string | null;
  };
  mjcf: {
    path: string | null;
    exportedLength: number | null;
    parsePassed: boolean;
    parseMessage: string | null;
    mujocoPyPassed: boolean | null;
    mujocoPyMessage: string | null;
  };
  usd: {
    path: string | null;
    openOk: boolean | null;
    jointMatchWithTruth: boolean | null;
    articulationValid: boolean | null;
    materialMatchWithTruth: boolean | null;
    failures: string[];
  };
  usda: {
    path: string | null;
    openOk: boolean | null;
    jointMatchWithTruth: boolean | null;
    articulationValid: boolean | null;
    materialMatchWithTruth: boolean | null;
    failures: string[];
  };
};

type FinalReport = {
  startedAt: string;
  finishedAt: string;
  options: ExecutionOptions;
  groups: number;
  groupSize: number;
  summary: {
    pass: number;
    partial: number;
    fail: number;
    candidateFixtures: number;
  };
  groupsReport: GroupReport[];
};

type JsonRecord = Record<string, unknown>;

type SourceContext = {
  importFiles: RobotFile[];
  allFileContents: Record<string, string>;
  supportRootAbs: string;
};

const DATASET_ROOTS: Record<DatasetName, string> = {
  unitree_ros: path.resolve('test/unitree_ros/robots'),
  'mujoco_menagerie-main': path.resolve('test/mujoco_menagerie-main'),
  'myosuite-main': path.resolve('test/myosuite-main'),
  unitree_ros_usda: path.resolve('test/unitree_ros_usda'),
  unitree_model: path.resolve('test/unitree_model'),
  awesome_robot_descriptions_repos: path.resolve('test/awesome_robot_descriptions_repos'),
};

const DATASET_ADDITIONAL_CONTEXT_ROOTS: Partial<Record<DatasetName, string[]>> = {
  'mujoco_menagerie-main': [path.resolve('test/mujoco_menagerie-main/assets')],
};

function printUsage(): void {
  process.stdout.write(`Usage:
  npx tsx scripts/test/truth/validate_assembled_fixture_exports.ts [options]

Options:
  --output <path>              Manifest output JSON path. Default: ${DEFAULT_OUTPUT_PATH}
  --artifacts-dir <path>       Artifact output root. Default: ${DEFAULT_ARTIFACT_DIR}
  --dataset <name>             Repeatable dataset filter. Supported: ${DATASET_NAMES.join(', ')}
  --match <token>              Repeatable token filter (entry path / id).
  --limit <n>                  Max number of fixtures imported before grouping.
  --group-size <n>             Number of components per assembly. Default: ${DEFAULT_GROUP_SIZE}
  --skip-isaac                 Skip IsaacSim checks for USD/USDA.
  --skip-mujoco                Skip mujoco python MJCF parse check.
  --isaac-python <path>        IsaacSim python executable. Default: ${DEFAULT_ISAAC_PYTHON}
  --isaaclab-root <path>       IsaacLab root for convert_urdf.py. Default: ${DEFAULT_ISAACLAB_ROOT}
  --mujoco-python <path>       Python executable used for mujoco module checks. Default: ${DEFAULT_MUJOCO_PYTHON}
  --help                       Show help.
`);
}

function fail(message: string): never {
  throw new Error(message);
}

function parseArgs(argv: string[]): ExecutionOptions {
  const options: ExecutionOptions = {
    outputPath: DEFAULT_OUTPUT_PATH,
    artifactsDir: DEFAULT_ARTIFACT_DIR,
    datasets: [...DATASET_NAMES],
    matches: [],
    limit: null,
    groupSize: DEFAULT_GROUP_SIZE,
    skipIsaacCheck: false,
    skipMujocoCheck: false,
    isaacPython: DEFAULT_ISAAC_PYTHON,
    isaacLabRoot: DEFAULT_ISAACLAB_ROOT,
    mujocoPython: DEFAULT_MUJOCO_PYTHON,
  };

  let datasetFilterSet = false;
  const nextValue = (indexRef: { value: number }): string => {
    const value = argv[indexRef.value + 1];
    if (!value) {
      fail(`Missing value for ${argv[indexRef.value]}`);
    }
    indexRef.value += 1;
    return value;
  };

  for (const indexRef = { value: 0 }; indexRef.value < argv.length; indexRef.value += 1) {
    const arg = argv[indexRef.value];
    switch (arg) {
      case '--output':
        options.outputPath = path.resolve(nextValue(indexRef));
        break;
      case '--artifacts-dir':
        options.artifactsDir = path.resolve(nextValue(indexRef));
        break;
      case '--dataset':
        const dataset = nextValue(indexRef);
        if (!DATASET_NAMES.includes(dataset as DatasetName)) {
          fail(`Unknown dataset: ${dataset}`);
        }
        if (!datasetFilterSet) {
          options.datasets = [];
          datasetFilterSet = true;
        }
        if (!options.datasets.includes(dataset as DatasetName)) {
          options.datasets.push(dataset as DatasetName);
        }
        break;
      case '--match':
        options.matches.push(nextValue(indexRef).trim().toLowerCase());
        break;
      case '--limit': {
        const value = Number.parseInt(nextValue(indexRef), 10);
        if (!Number.isFinite(value) || value < 0) {
          fail(`Invalid --limit: ${value}`);
        }
        options.limit = value;
        break;
      }
      case '--group-size': {
        const value = Number.parseInt(nextValue(indexRef), 10);
        if (!Number.isFinite(value) || value < 1 || !Number.isInteger(value)) {
          fail(`Invalid --group-size: ${value}`);
        }
        options.groupSize = value;
        break;
      }
      case '--skip-isaac':
        options.skipIsaacCheck = true;
        break;
      case '--skip-mujoco':
        options.skipMujocoCheck = true;
        break;
      case '--isaac-python':
        options.isaacPython = path.resolve(nextValue(indexRef));
        break;
      case '--isaaclab-root':
        options.isaacLabRoot = path.resolve(nextValue(indexRef));
        break;
      case '--mujoco-python':
        options.mujocoPython = path.resolve(nextValue(indexRef));
        break;
      case '--help':
      case '-h':
        printUsage();
        process.exit(0);
        break;
      default:
        fail(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function normalizePosix(filePath: string): string {
  return filePath.replace(/\\/g, '/').replace(/^\/+/, '');
}

function toDatasetRoot(dataset: DatasetName): string {
  return DATASET_ROOTS[dataset];
}

async function collectFiles(absoluteRoot: string): Promise<string[]> {
  const entries = await fsPromises.readdir(absoluteRoot, { withFileTypes: true });
  const collected: string[] = [];
  for (const entry of entries.toSorted((left, right) => left.name.localeCompare(right.name))) {
    if (entry.name.startsWith('.')) {
      continue;
    }
    const absolutePath = path.join(absoluteRoot, entry.name);
    if (entry.isDirectory()) {
      collected.push(...(await collectFiles(absolutePath)));
      continue;
    }
    if (entry.isFile()) {
      collected.push(absolutePath);
    }
  }
  return collected;
}

function shouldCaptureText(absolutePath: string): boolean {
  return TEXT_CONTENT_EXTENSIONS.has(path.extname(absolutePath).toLowerCase());
}

function shouldCaptureAsset(absolutePath: string): boolean {
  return ASSET_EXTENSIONS.has(path.extname(absolutePath).toLowerCase());
}

function guessMimeType(filePath: string): string {
  const extension = path.extname(filePath).toLowerCase();
  switch (extension) {
    case '.dae':
      return 'model/vnd.collada+xml';
    case '.gltf':
      return 'model/gltf+json';
    case '.glb':
      return 'model/gltf-binary';
    case '.jpg':
    case '.jpeg':
      return 'image/jpeg';
    case '.png':
      return 'image/png';
    case '.stl':
      return 'model/stl';
    case '.svg':
      return 'image/svg+xml';
    case '.webp':
      return 'image/webp';
    case '.bmp':
      return 'image/bmp';
    case '.gif':
      return 'image/gif';
    default:
      return 'application/octet-stream';
  }
}

async function buildSourceContext(dataset: DatasetName, supportRootAbs: string, fixtureDatasetRoot: string): Promise<SourceContext> {
  const importFileMap = new Map<string, RobotFile>();
  const allFileContents: Record<string, string> = {};
  const rootsToScan = [supportRootAbs, ...(DATASET_ADDITIONAL_CONTEXT_ROOTS[dataset] ?? [])].filter(
    Boolean,
  ) as string[];

  for (const root of rootsToScan) {
    if (!fs.existsSync(root)) {
      continue;
    }
    const files = await collectFiles(root);
    for (const absolutePath of files) {
      if (!shouldCaptureText(absolutePath)) {
        continue;
      }

      const relativePath = normalizePosix(path.relative(fixtureDatasetRoot, absolutePath));
      try {
        const content = await fsPromises.readFile(absolutePath, 'utf8');
        allFileContents[relativePath] = content;
        const format = detectImportFormat(content, relativePath);
        if (format && (format === 'urdf' || format === 'mjcf' || format === 'xacro' || format === 'sdf')) {
          importFileMap.set(relativePath, {
            name: relativePath,
            content,
            format,
          });
        }
      } catch {
        // skip unreadable file
      }
    }
  }

  const importFiles = Array.from(importFileMap.values()).sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  return {
    importFiles,
    allFileContents,
    supportRootAbs,
  };
};

function resolveSupportRootPathMap(
  fixture: FixtureSummary,
): { datasetRoot: string; supportRootAbs: string; supportRootRel: string } {
  const datasetRoot = toDatasetRoot(fixture.dataset);
  const supportRootRel = fixture.supportRoot || '.';
  return {
    datasetRoot,
    supportRootAbs: path.resolve(datasetRoot, supportRootRel),
    supportRootRel,
  };
}

async function resolveFixtureImport(
  fixture: FixtureSummary,
  context: SourceContext,
): Promise<FixtureImportResult> {
  const normalizedEntryPath = normalizePosix(fixture.entryPath);
  const file = context.importFiles.find((candidate) => candidate.name === normalizedEntryPath);
  if (!file) {
    return { kind: 'error', message: `Missing fixture import file: ${fixture.entryPath}` };
  }

  let result;
  try {
    result = resolveRobotFileData(file, {
      availableFiles: context.importFiles,
      allFileContents: context.allFileContents,
    });
  } catch (error) {
    return { kind: 'error', message: `ResolveRobotFileData threw: ${String(error)}` };
  }
  if (result.status !== 'ready') {
    return { kind: 'error', message: `ResolveRobotFileData status: ${result.status}` };
  }
  return {
    kind: 'ok',
    file,
    robotData: result.robotData,
  };
}

function makeBridgeJoint(parent: AssemblyComponent, child: AssemblyComponent, bridgeId: string): BridgeJoint {
  const fixedJoint = {
    ...DEFAULT_JOINT,
    id: `${bridgeId}_joint`,
    name: `${bridgeId}_joint`,
    type: JointType.FIXED,
    parentLinkId: parent.robot.rootLinkId,
    childLinkId: child.robot.rootLinkId,
    origin: {
      xyz: { x: 0, y: 0, z: 0 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  };

  return {
    id: bridgeId,
    name: `${bridgeId}_name`,
    parentComponentId: parent.id,
    parentLinkId: parent.robot.rootLinkId,
    childComponentId: child.id,
    childLinkId: child.robot.rootLinkId,
    joint: {
      ...fixedJoint,
      limit: {
        lower: 0,
        upper: 0,
        effort: 0,
        velocity: 0,
      },
      axis: undefined,
    },
  };
}

function toRobotStateData(robotData: RobotData): RobotData & {
  selection: {
    selectedLinkIds: Set<string>;
    selectedJointIds: Set<string>;
    hoveredLinkId: string | null;
    hoveredJointId: string | null;
  };
} {
  return {
    ...robotData,
    selection: {
      selectedLinkIds: new Set<string>(),
      selectedJointIds: new Set<string>(),
      hoveredLinkId: null,
      hoveredJointId: null,
    },
  };
}

function writeArchiveFiles(exportDir: string, archiveFiles: Map<string, Blob>): Promise<void> {
  return Promise.all(
    Array.from(archiveFiles.entries()).map(async ([archivePath, blob]) => {
      const absolutePath = path.join(exportDir, archivePath);
      await fsPromises.mkdir(path.dirname(absolutePath), { recursive: true });
      const data = new Uint8Array(await blob.arrayBuffer());
      await fsPromises.writeFile(absolutePath, data);
    }),
  ).then(() => undefined);
}

function chunkArray<T>(items: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

async function runProcess(command: string, args: string[], options: { cwd: string; logPath: string; env?: NodeJS.ProcessEnv; }): Promise<number> {
  await fsPromises.mkdir(path.dirname(options.logPath), { recursive: true });
  return await new Promise<number>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const log = fs.createWriteStream(options.logPath, { encoding: 'utf-8' });
    child.stdout.on('data', (chunk) => log.write(chunk));
    child.stderr.on('data', (chunk) => log.write(chunk));
    child.on('error', (error) => {
      log.end();
      reject(error);
    });
    child.on('close', (code) => {
      log.end();
      resolve(code ?? 1);
    });
  });
}

async function runJsonProcess(params: {
  command: string;
  args: string[];
  cwd: string;
  env?: NodeJS.ProcessEnv;
  logPath: string;
  outputPath: string;
}): Promise<JsonRecord> {
  const code = await runProcess(params.command, params.args, {
    cwd: params.cwd,
    env: params.env,
    logPath: params.logPath,
  });
  if (code !== 0) {
    throw new Error(`Command failed (${code}): ${params.command} ${params.args.join(' ')}`);
  }
  if (!fs.existsSync(params.outputPath)) {
    throw new Error(`Missing JSON output file: ${params.outputPath}`);
  }
  const payload = await fsPromises.readFile(params.outputPath, 'utf8');
  return JSON.parse(payload) as JsonRecord;
}

async function runIsaacInspectionTool(
  command: string,
  pythonPath: string,
  isaacLabRoot: string,
  stagePaths: string[],
  outputPath: string,
  logPath: string,
): Promise<JsonRecord> {
  return await runJsonProcess({
    command: pythonPath,
    args: [command, ...stagePaths, '--output', outputPath, '--headless'],
    cwd: path.resolve('.'),
    env: {
      ...process.env,
      PYTHONPATH: isaacLabRoot,
    },
    logPath,
    outputPath,
  });
}

function materialColorTuple(value: unknown): [number, number, number] | null {
  if (!Array.isArray(value) || value.length < 3) {
    return null;
  }
  const [r, g, b] = value.map((entry) => Number(entry));
  if ([r, g, b].some((entry) => !Number.isFinite(entry))) {
    return null;
  }
  return [Number(r.toFixed(6)), Number(g.toFixed(6)), Number(b.toFixed(6))];
}

function normalizeMaterialSignatures(raw: unknown): ParsedMaterialSignature[] {
  const signatures: ParsedMaterialSignature[] = [];
  if (!raw || typeof raw !== 'object') {
    return signatures;
  }

  const entries = (raw as JsonRecord).visibleAppearanceSignatures;
  if (Array.isArray(entries)) {
    for (const entry of entries) {
      if (!entry || typeof entry !== 'object') {
        continue;
      }
      const parsed = entry as { color?: unknown; textured?: unknown };
      const tuple = materialColorTuple(parsed.color);
      const textured = Boolean(parsed.textured);
      signatures.push({ color: tuple, textured });
    }
    return signatures;
  }

  const colors = Array.isArray((raw as JsonRecord).visibleMaterialColors)
    ? (raw as JsonRecord).visibleMaterialColors
    : [];
  if (Array.isArray(colors)) {
    colors.forEach((entry) => {
      const tuple = materialColorTuple(entry);
      if (tuple) {
        signatures.push({ color: tuple, textured: false });
      }
    });
  }
  return signatures;
}

function signatureDistance(left: ParsedMaterialSignature, right: ParsedMaterialSignature): number {
  if (!left.color || !right.color) {
    return left.color === right.color && left.textured === right.textured ? 0 : Number.POSITIVE_INFINITY;
  }
  if (left.textured !== right.textured) {
    return Number.POSITIVE_INFINITY;
  }
  return Math.max(
    Math.abs(left.color[0] - right.color[0]),
    Math.abs(left.color[1] - right.color[1]),
    Math.abs(left.color[2] - right.color[2]),
  );
}

function compareMaterialSignatures(
  left: ParsedMaterialSignature[],
  right: ParsedMaterialSignature[],
  tolerance: number,
): { unmatchedLeft: ParsedMaterialSignature[]; unmatchedRight: ParsedMaterialSignature[] } {
  const remainingRight = [...right];
  const unmatchedLeft: ParsedMaterialSignature[] = [];

  left.forEach((leftEntry) => {
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    for (let index = 0; index < remainingRight.length; index += 1) {
      const distance = signatureDistance(leftEntry, remainingRight[index] as ParsedMaterialSignature);
      if (distance < bestDistance) {
        bestDistance = distance;
        bestIndex = index;
      }
    }
    if (bestIndex === -1 || bestDistance > tolerance) {
      unmatchedLeft.push(leftEntry);
      return;
    }
    remainingRight.splice(bestIndex, 1);
  });

  return {
    unmatchedLeft,
    unmatchedRight: remainingRight,
  };
}

function asNumberOrNull(value: unknown): number | null {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }

  return numeric;
}

function pickMujocoMeshFileReferences(mjcf: string): string[] {
  const references = new Set<string>();
  const meshAssetRegex = /<mesh\b[^>]*\bfile\s*=\s*["']([^"']+)["'][^>]*>/g;
  let match = meshAssetRegex.exec(mjcf);
  while (match) {
    const file = (match[1] || '').trim();
    if (file && !file.startsWith('$(')) {
      references.add(file);
    }
    match = meshAssetRegex.exec(mjcf);
  }
  return [...references];
}

function normalizeAssetLookupPath(filePath: string): string {
  return filePath
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .replace(/^(\.\/)+/, '')
    .trim();
}

function findMeshBlob(meshPath: string, meshMap: Map<string, Blob>): Blob | null {
  const normalized = normalizeAssetLookupPath(meshPath).toLowerCase();
  const candidates = Array.from(meshMap.entries()).map(([alias, blob]) => [normalizeAssetLookupPath(alias).toLowerCase(), blob]);

  const direct = candidates.find(([alias]) => alias === normalized)?.[1];
  if (direct) {
    return direct;
  }

  const normalizedBase = path.basename(normalized).toLowerCase();
  for (const [alias, blob] of candidates) {
    if (
      alias === normalized ||
      alias === normalizedBase ||
      alias.endsWith(`/${normalized}`) ||
      alias.endsWith(`/${normalizedBase}`) ||
      normalized.endsWith(`/${alias}`)
    ) {
      return blob;
    }
  }

  return null;
}

async function stageMujocoMeshes(
  groupDir: string,
  mjcf: string,
  meshMap: Map<string, Blob>,
): Promise<void> {
  const meshDir = path.join(groupDir, 'meshes');
  await fsPromises.rm(meshDir, { recursive: true, force: true });
  await fsPromises.mkdir(meshDir, { recursive: true });

  const files = pickMujocoMeshFileReferences(mjcf);
  const missing: string[] = [];
  for (const file of files) {
    const blob = findMeshBlob(file, meshMap);
    if (!blob) {
      missing.push(file);
      continue;
    }

    const normalizedFile = normalizeAssetLookupPath(file);
    const destination = path.join(meshDir, normalizedFile);
    await ensureFileDirectory(destination);
    const data = new Uint8Array(await blob.arrayBuffer());
    await fsPromises.writeFile(destination, data);
  }

  if (missing.length > 0) {
    throw new Error(`Missing mesh assets for MJCF parse: ${missing.join(', ')}`);
  }
}

function chooseBestAttempt(rawSummary: unknown): JsonRecord | null {
  if (!rawSummary || typeof rawSummary !== 'object') {
    return null;
  }
  const summary = rawSummary as JsonRecord;
  const candidates = Array.isArray(summary.attempts) ? (summary.attempts as unknown[]) : [];
  const initialized = candidates
    .map((entry) => (typeof entry === 'object' ? (entry as JsonRecord) : null))
    .filter((entry): entry is JsonRecord => entry !== null && entry.initialized === true);
  if (initialized.length === 0) {
    return null;
  }
  initialized.sort((left, right) => {
    const leftDof = Number.isFinite(Number(left.num_dof)) ? Number(left.num_dof) : -1;
    const rightDof = Number.isFinite(Number(right.num_dof)) ? Number(right.num_dof) : -1;
    if (leftDof !== rightDof) {
      return rightDof - leftDof;
    }
    const leftBody = Number.isFinite(Number(left.body_count)) ? Number(left.body_count) : -1;
    const rightBody = Number.isFinite(Number(right.body_count)) ? Number(right.body_count) : -1;
    return rightBody - leftBody;
  });
  return initialized[0] ?? null;
}

function evaluateIsaacComparison(params: {
  stageSummary: JsonRecord;
  articulationSummary: JsonRecord;
  materialSummary: JsonRecord;
  currentPath: string;
  truthPath: string;
}): {
  passed: boolean;
  failures: string[];
  articulationValid: boolean;
  colorMatch: boolean;
  jointMatch: boolean;
  openOk: boolean;
} {
  const currentStage = (params.stageSummary[params.currentPath] || {}) as JsonRecord;
  const truthStage = (params.stageSummary[params.truthPath] || {}) as JsonRecord;
  const currentArt = (params.articulationSummary[params.currentPath] || {}) as JsonRecord;
  const truthArt = (params.articulationSummary[params.truthPath] || {}) as JsonRecord;
  const currentMat = (params.materialSummary[params.currentPath] || {}) as JsonRecord;
  const truthMat = (params.materialSummary[params.truthPath] || {}) as JsonRecord;

  const failures: string[] = [];
  const currentOpenOk = currentStage.open_ok === true;
  const truthOpenOk = truthStage.open_ok === true;
  if (!currentOpenOk) {
    failures.push('Current stage failed to open');
  }
  if (!truthOpenOk) {
    failures.push('Truth stage failed to open');
  }
  const currentJointCount =
    asNumberOrNull(currentStage.joint_count_non_fixed) ??
    asNumberOrNull(currentStage.joint_count) ??
    0;
  const truthJointCount =
    asNumberOrNull(truthStage.joint_count_non_fixed) ??
    asNumberOrNull(truthStage.joint_count) ??
    0;
  if (currentJointCount !== truthJointCount) {
    failures.push(
      `Joint count mismatch: current=${currentJointCount} truth=${truthJointCount}`,
    );
  }
  const currentBodyCount = Number(currentStage.rigid_body_count || 0);
  const truthBodyCount = Number(truthStage.rigid_body_count || 0);
  if (currentBodyCount !== truthBodyCount) {
    failures.push(`Rigid body count mismatch: current=${currentBodyCount} truth=${truthBodyCount}`);
  }
  if (currentOpenOk && Number(currentStage.invalid_joint_target_count || 0) > 0) {
    failures.push(`Current stage has invalid joint targets`);
  }

  const currentAttempt = chooseBestAttempt(currentArt);
  const truthAttempt = chooseBestAttempt(truthArt);
  const currentAttemptDof = asNumberOrNull(currentAttempt?.num_dof);
  const truthAttemptDof = asNumberOrNull(truthAttempt?.num_dof);
  const currentAttemptBody = asNumberOrNull(currentAttempt?.body_count);
  const truthAttemptBody = asNumberOrNull(truthAttempt?.body_count);

  const articulationValid = currentAttempt !== null && truthAttempt !== null;
  if (!articulationValid) {
    failures.push('Missing valid articulation initialization');
  }
  const currentCandidate = String(currentAttempt?.candidate || '').trim();
  const truthCandidate = String(truthAttempt?.candidate || '').trim();
  if (currentAttempt && truthAttempt && currentCandidate !== truthCandidate) {
    failures.push(`Articulation root mismatch: current=${currentCandidate} truth=${truthCandidate}`);
  }
  if (
    currentAttemptDof !== null &&
    truthAttemptDof !== null &&
    currentAttemptDof !== truthAttemptDof
  ) {
    failures.push(`DOF mismatch: current=${currentAttemptDof} truth=${truthAttemptDof}`);
  }
  if (
    currentAttemptBody !== null &&
    truthAttemptBody !== null &&
    currentAttemptBody !== truthAttemptBody
  ) {
    failures.push(`Body count mismatch: current=${currentAttemptBody} truth=${truthAttemptBody}`);
  }

  const currentMaterialSignatures = currentOpenOk && truthOpenOk ? normalizeMaterialSignatures(currentMat) : [];
  const truthMaterialSignatures = currentOpenOk && truthOpenOk ? normalizeMaterialSignatures(truthMat) : [];
  const materialCompare = compareMaterialSignatures(
    currentMaterialSignatures,
    truthMaterialSignatures,
    DEFAULT_COLOR_TOLERANCE,
  );
  const colorMatch = materialCompare.unmatchedLeft.length === 0 && materialCompare.unmatchedRight.length === 0;
  const openOk = currentOpenOk && truthOpenOk;
  const jointMatch =
    openOk &&
    currentJointCount === truthJointCount &&
    currentBodyCount === truthBodyCount &&
    Number(currentStage.invalid_joint_target_count || 0) === 0;
  if (!colorMatch) {
    failures.push('Material appearance mismatch against truth');
  }

  return {
    passed: failures.length === 0,
    failures,
    articulationValid,
    colorMatch,
    jointMatch,
    openOk,
  };
}

async function checkMujocoPy(python: string, mjcfPath: string, logPath: string): Promise<{ passed: boolean; message: string | null }> {
  const script = [
    'import sys',
    'import mujoco',
    'import argparse',
    '',
    'parser = argparse.ArgumentParser()',
    'parser.add_argument("path")',
    'args = parser.parse_args()',
    'm = mujoco.MjModel.from_xml_path(args.path)',
    'if m is None:',
    '    raise RuntimeError("mujoco returned empty model")',
    'print("ok")',
  ].join('\n');
  const tmpScript = path.join(process.cwd(), '.tmp-mujoco-check.py');
  await fsPromises.writeFile(tmpScript, script, 'utf8');
  const code = await runProcess(python, [tmpScript, mjcfPath], {
    cwd: path.dirname(mjcfPath),
    logPath,
    env: process.env,
  });
  await fsPromises.rm(tmpScript, { force: true });
  if (code !== 0) {
    return {
      passed: false,
      message: `mujoco parse failed (exit ${code})`,
    };
  }
  return { passed: true, message: null };
}

function collectFixtureMeshes(
  fixture: FixtureSummary,
  context: SourceContext,
  datasetRoot: string,
  supportRootAbs: string,
): Array<[string, Blob]> {
  const packageName = path.basename(supportRootAbs);
  const datasetRelativeFixturePath = normalizePosix(fixture.entryPath);
  const result: Array<[string, Blob]> = [];
  const roots = [supportRootAbs, ...(DATASET_ADDITIONAL_CONTEXT_ROOTS[fixture.dataset] ?? [])];
  const seenPaths = new Set<string>();

  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    const files = fs
      .readdirSync(root, { withFileTypes: true })
      .sort((left, right) => left.name.localeCompare(right.name));
    const walk = (relativeDir: string, entries: fs.Dirent[]): void => {
      for (const entry of entries) {
        const absolutePath = path.join(root, relativeDir, entry.name);
        if (entry.isDirectory()) {
          walk(path.join(relativeDir, entry.name), fs.readdirSync(absolutePath, { withFileTypes: true }));
          continue;
        }
        if (!shouldCaptureAsset(absolutePath)) {
          continue;
        }
        const datasetRelativePath = normalizePosix(path.relative(datasetRoot, absolutePath));
        const localRelativePath = normalizePosix(path.relative(supportRootAbs, absolutePath));
        const entryRelativePath = normalizePosix(path.relative(path.posix.dirname(datasetRelativeFixturePath), datasetRelativePath));
        const aliases = [
          localRelativePath,
          datasetRelativePath,
          localRelativePath === '' ? path.basename(absolutePath) : localRelativePath,
          entryRelativePath,
          `${packageName}/${localRelativePath}`,
          `package://${packageName}/${localRelativePath}`,
        ]
          .map((value) => value.replace(/^\/+/, ''))
          .filter((value) => value && value !== '.');
        const data = fs.readFileSync(absolutePath);
        const blob = new Blob([data], { type: guessMimeType(absolutePath) });
        aliases.forEach((alias) => {
          if (!seenPaths.has(alias)) {
            seenPaths.add(alias);
            result.push([alias, blob]);
          }
        });
      }
    };
    walk('', files);
  }
  return result;
}

function ensureFileDirectory(filePath: string): Promise<void> {
  return fsPromises.mkdir(path.dirname(filePath), { recursive: true });
}

function writeTextFile(filePath: string, content: string): Promise<void> {
  return ensureFileDirectory(filePath).then(() => fsPromises.writeFile(filePath, content, 'utf8'));
}

async function buildAssemblyForGroup(
  fixtures: FixtureSummary[],
  contexts: Map<string, SourceContext>,
  options: ExecutionOptions,
  groupIndex: number,
): Promise<GroupReport> {
  const groupId = `assembly_${String(groupIndex + 1).padStart(3, '0')}`;
  const groupDir = path.join(options.artifactsDir, groupId);
  await fsPromises.mkdir(groupDir, { recursive: true });
  drainUnhandledRejections();

  const imported: PreparedFixture[] = [];
  const failures: string[] = [];

  for (const fixture of fixtures) {
    const key = `${fixture.dataset}::${fixture.supportRoot || '.'}`;
    const context = contexts.get(key);
    if (!context) {
      failures.push(`Missing context for ${fixture.entryPath}`);
      continue;
    }
    const resolved = await resolveFixtureImport(fixture, context);
    if (resolved.kind === 'error') {
      failures.push(`Failed to import fixture ${fixture.entryPath}: ${resolved.message}`);
      continue;
    }
    const { file, robotData } = resolved;
    const componentIdentity = buildAssemblyComponentIdentity({
      fileName: file.name,
      existingComponentIds: imported.map((entry) => entry.componentIdentity.componentId),
      existingComponentNames: imported.map((entry) => entry.componentIdentity.componentName),
    });
    const prepared = prepareAssemblyRobotData(robotData, {
      componentId: componentIdentity.componentId,
      rootName: componentIdentity.displayName,
      sourceFilePath: file.name,
      sourceFormat: file.format,
    });
    imported.push({
      summary: fixture,
      file,
      robotData: prepared,
      context,
      componentIdentity: {
        componentId: componentIdentity.componentId,
        componentName: componentIdentity.displayName,
      },
    });
  }

  const components = imported.map((entry): AssemblyComponent => {
    return {
      id: entry.componentIdentity.componentId,
      name: entry.componentIdentity.componentName,
      sourceFile: entry.file.name,
      robot: entry.robotData,
    };
  });

  if (components.length === 0) {
    return {
      groupId,
      sourceEntries: fixtures.map((entry) => entry.entryPath),
      sourceDatasets: [...new Set(fixtures.map((entry) => entry.dataset))],
      status: 'fail',
      failures: [...failures, 'No valid components for assembly'],
      urdf: { path: null, exportedLength: null, parsePassed: false, parseMessage: 'No components' },
      mjcf: { path: null, exportedLength: null, parsePassed: false, parseMessage: 'No components', mujocoPyPassed: null, mujocoPyMessage: null },
      usd: { path: null, openOk: null, jointMatchWithTruth: null, articulationValid: null, materialMatchWithTruth: null, failures: [] },
      usda: { path: null, openOk: null, jointMatchWithTruth: null, articulationValid: null, materialMatchWithTruth: null, failures: [] },
    };
  }

  const bridges: Record<string, BridgeJoint> = {};
  for (let index = 0; index + 1 < components.length; index += 1) {
    const parent = components[index];
    const child = components[index + 1];
    bridges[`bridge_${index}`] = makeBridgeJoint(parent, child, `bridge_${groupId}_${index}`);
  }

  const assemblyState: AssemblyState = {
    name: groupId,
    components: Object.fromEntries(components.map((component) => [component.id, component])),
    bridges,
  };
  const exportableRobot = buildExportableAssemblyRobotData(assemblyState);
  const robotState = toRobotStateData(exportableRobot);

  const urdfPath = path.join(groupDir, 'assembly.urdf');
  const mjcfPath = path.join(groupDir, 'assembly.xml');
  const usdExportDir = path.join(groupDir, 'usd');
  const usdaExportDir = path.join(groupDir, 'usda');

  const report: GroupReport = {
    groupId,
    sourceEntries: fixtures.map((entry) => entry.entryPath),
    sourceDatasets: [...new Set(fixtures.map((entry) => entry.dataset))],
    status: 'pass',
    failures: [...failures],
    urdf: { path: urdfPath, exportedLength: null, parsePassed: false, parseMessage: null },
    mjcf: {
      path: mjcfPath,
      exportedLength: null,
      parsePassed: false,
      parseMessage: null,
      mujocoPyPassed: null,
      mujocoPyMessage: null,
    },
    usd: { path: null, openOk: null, jointMatchWithTruth: null, articulationValid: null, materialMatchWithTruth: null, failures: [] },
    usda: { path: null, openOk: null, jointMatchWithTruth: null, articulationValid: null, materialMatchWithTruth: null, failures: [] },
  };

  const fixtureDatasetRoots = fixtures.map((fixture) => {
    const { datasetRoot, supportRootAbs } = resolveSupportRootPathMap(fixture);
    return { fixture, datasetRoot, supportRootAbs };
  });
  const meshEntries = fixtureDatasetRoots.flatMap(({ fixture, datasetRoot, supportRootAbs }) => {
    const context = contexts.get(`${fixture.dataset}::${fixture.supportRoot || '.'}`);
    if (!context) {
      return [];
    }
    return collectFixtureMeshes(fixture, context, datasetRoot, supportRootAbs);
  });
  const meshMap = new Map<string, Blob>(meshEntries);

  try {
    const generatedUrdf = generateURDF(robotState, false);
    await writeTextFile(urdfPath, generatedUrdf);
    report.urdf.exportedLength = generatedUrdf.length;
    const urdfParse = resolveRobotFileData({
      name: path.basename(urdfPath),
      content: generatedUrdf,
      format: 'urdf',
    });
    report.urdf.parsePassed = urdfParse.status === 'ready';
    report.urdf.parseMessage = report.urdf.parsePassed
      ? null
      : `URDF re-import failed: ${urdfParse.status}`;
    if (!report.urdf.parsePassed) {
      report.status = report.status === 'fail' ? 'fail' : 'partial';
      report.failures.push(report.urdf.parseMessage ?? 'URDF re-import failed');
    }
  } catch (error) {
    report.urdf.parsePassed = false;
    report.urdf.parseMessage = String(error);
    report.status = report.status === 'fail' ? 'fail' : 'partial';
    report.failures.push(`URDF export failure: ${String(error)}`);
  }
  await yieldToEventLoop();
  recordUnhandledRejectionFailures('URDF export', report);

  try {
    const generatedMjcf = generateMujocoXML(robotState, {
      meshdir: 'meshes/',
      includeSceneHelpers: false,
    });
    await stageMujocoMeshes(groupDir, generatedMjcf, meshMap);
    await writeTextFile(mjcfPath, generatedMjcf);
    report.mjcf.exportedLength = generatedMjcf.length;
    const mjcfParse = resolveRobotFileData({
      name: path.basename(mjcfPath),
      content: generatedMjcf,
      format: 'mjcf',
    });
    report.mjcf.parsePassed = mjcfParse.status === 'ready';
    report.mjcf.parseMessage = report.mjcf.parsePassed
      ? null
      : `MJCF re-import failed: ${mjcfParse.status}`;
    if (!report.mjcf.parsePassed) {
      report.status = 'partial';
      report.failures.push(`MJCF parse failed: ${report.mjcf.parseMessage}`);
    }
  } catch (error) {
    report.mjcf.parsePassed = false;
    report.mjcf.parseMessage = String(error);
    report.status = 'fail';
    report.failures.push(`MJCF export failure: ${String(error)}`);
  }
  await yieldToEventLoop();
  recordUnhandledRejectionFailures('MJCF export', report);

  const usdStagePaths: { currentUsa?: string; currentUsda?: string } = {};
  try {
    const payload = await exportRobotToUsd({
      robot: robotState,
      exportName: groupId,
      assets: {},
      extraMeshFiles: meshMap,
      meshCompression: {
        enabled: true,
        quality: DEFAULT_MESH_QUALITY,
      },
      layoutProfile: 'isaacsim',
      fileFormat: 'usd',
    });
    await writeArchiveFiles(usdExportDir, payload.archiveFiles);
    report.usd.path = path.resolve(usdExportDir, payload.rootLayerPath);
    report.usd.openOk = null;
    usdStagePaths.currentUsa = report.usd.path;
  } catch (error) {
    report.usd.path = null;
    report.usd.failures.push(String(error));
    report.status = 'fail';
    report.failures.push(`USD export failure: ${String(error)}`);
  }
  await yieldToEventLoop();
  recordUnhandledRejectionFailures('USD export', report, report.usd.failures);

  try {
    const payload = await exportRobotToUsd({
      robot: robotState,
      exportName: groupId,
      assets: {},
      extraMeshFiles: meshMap,
      meshCompression: {
        enabled: true,
        quality: DEFAULT_MESH_QUALITY,
      },
      layoutProfile: 'isaacsim',
      fileFormat: 'usda',
    });
    await writeArchiveFiles(usdaExportDir, payload.archiveFiles);
    report.usda.path = path.resolve(usdaExportDir, payload.rootLayerPath);
    report.usda.openOk = null;
    usdStagePaths.currentUsda = report.usda.path;
  } catch (error) {
    report.usda.path = null;
    report.usda.failures.push(String(error));
    report.status = report.status === 'pass' ? 'partial' : report.status;
    report.failures.push(`USDA export failure: ${String(error)}`);
  }
  await yieldToEventLoop();
  recordUnhandledRejectionFailures('USDA export', report, report.usda.failures);

  if (options.skipIsaacCheck) {
    await yieldToEventLoop();
    recordUnhandledRejectionFailures('Pre-summary', report);
    return report;
  }

  const truthStageUsaPath = path.join(groupDir, 'truth_from_urdf.usda');
  try {
    await runProcess(options.isaacPython, [
      path.join(options.isaacLabRoot, 'scripts/tools/convert_urdf.py'),
      urdfPath,
      truthStageUsaPath,
      '--headless',
    ], {
      cwd: options.isaacLabRoot,
      env: {
        ...process.env,
        PYTHONPATH: options.isaacLabRoot,
      },
      logPath: path.join(groupDir, 'truth_from_urdf.log'),
    });
  } catch (error) {
    report.status = 'partial';
    report.failures.push(`Truth USD conversion failed: ${String(error)}`);
  }
  await yieldToEventLoop();
  recordUnhandledRejectionFailures('Isaac conversion', report);

  const inspectIsaac = async (
    label: 'usd' | 'usda',
    stagePath: string,
    outputPrefix: string,
  ): Promise<void> => {
    const stageScript = path.resolve('scripts/tools/isaacsim/inspect_isaacsim_usd_stage.py');
    const articulationScript = path.resolve('scripts/tools/isaacsim/inspect_isaacsim_articulation.py');
    const materialScript = path.resolve('scripts/tools/isaacsim/inspect_isaacsim_materials.py');
    const physicsScript = path.resolve('scripts/tools/isaacsim/inspect_isaacsim_physics_properties.py');

    try {
      const stageSummary = await runIsaacInspectionTool(
        stageScript,
        options.isaacPython,
        options.isaacLabRoot,
        [stagePath, truthStageUsaPath],
        path.join(groupDir, `${outputPrefix}_stage_summary.json`),
        path.join(groupDir, `${outputPrefix}_stage.log`),
      );
      const articulationSummary = await runIsaacInspectionTool(
        articulationScript,
        options.isaacPython,
        options.isaacLabRoot,
        [stagePath, truthStageUsaPath],
        path.join(groupDir, `${outputPrefix}_articulation_summary.json`),
        path.join(groupDir, `${outputPrefix}_articulation.log`),
      );
      const materialSummary = await runIsaacInspectionTool(
        materialScript,
        options.isaacPython,
        options.isaacLabRoot,
        [stagePath, truthStageUsaPath],
        path.join(groupDir, `${outputPrefix}_material_summary.json`),
        path.join(groupDir, `${outputPrefix}_material.log`),
      );
      const physicsSummary = await runIsaacInspectionTool(
        physicsScript,
        options.isaacPython,
        options.isaacLabRoot,
        [stagePath, truthStageUsaPath],
        path.join(groupDir, `${outputPrefix}_physics_summary.json`),
        path.join(groupDir, `${outputPrefix}_physics.log`),
      );

      const evalResult = evaluateIsaacComparison({
        stageSummary,
        articulationSummary,
        materialSummary,
        currentPath: stagePath,
        truthPath: truthStageUsaPath,
      });

      if (label === 'usd') {
        report.usd.openOk = evalResult.openOk;
        report.usd.jointMatchWithTruth = evalResult.jointMatch;
        report.usd.articulationValid = evalResult.articulationValid;
        report.usd.materialMatchWithTruth = evalResult.colorMatch;
      } else {
        report.usda.openOk = evalResult.openOk;
        report.usda.jointMatchWithTruth = evalResult.jointMatch;
        report.usda.articulationValid = evalResult.articulationValid;
        report.usda.materialMatchWithTruth = evalResult.colorMatch;
      }

      if (!evalResult.passed) {
        report.status = report.status === 'pass' ? 'partial' : report.status;
        if (label === 'usd') {
          report.usd.failures.push(...evalResult.failures);
        } else {
          report.usda.failures.push(...evalResult.failures);
        }
        report.failures.push(...evalResult.failures);
      }
      if (physicsSummary[stagePath] === undefined) {
        if (label === 'usd') {
          report.usd.failures.push('Missing physics inspection output');
        } else {
          report.usda.failures.push('Missing physics inspection output');
        }
      }
      await yieldToEventLoop();
      if (label === 'usd') {
        recordUnhandledRejectionFailures('Isaac USD inspection', report, report.usd.failures);
      } else {
        recordUnhandledRejectionFailures('Isaac USDA inspection', report, report.usda.failures);
      }
    } catch (error) {
      report.status = report.status === 'pass' ? 'partial' : report.status;
      const message = `${label.toUpperCase()} inspection failed: ${String(error)}`;
      if (label === 'usd') {
        report.usd.failures.push(message);
      } else {
        report.usda.failures.push(message);
      }
      report.failures.push(message);
      await yieldToEventLoop();
      if (label === 'usd') {
        recordUnhandledRejectionFailures('Isaac USD inspection', report, report.usd.failures);
      } else {
        recordUnhandledRejectionFailures('Isaac USDA inspection', report, report.usda.failures);
      }
    }
  };

  if (usdStagePaths.currentUsa && fs.existsSync(truthStageUsaPath) && fs.existsSync(usdStagePaths.currentUsa)) {
    await inspectIsaac('usd', usdStagePaths.currentUsa, 'usd');
  }

  if (usdStagePaths.currentUsda && fs.existsSync(truthStageUsaPath) && fs.existsSync(usdStagePaths.currentUsda)) {
    await inspectIsaac('usda', usdStagePaths.currentUsda, 'usda');
  }

  if (!options.skipMujocoCheck) {
    try {
      const mjcfToMujoco = await checkMujocoPy(options.mujocoPython, mjcfPath, path.join(groupDir, 'mujoco_py_check.log'));
      report.mjcf.mujocoPyPassed = mjcfToMujoco.passed;
      report.mjcf.mujocoPyMessage = mjcfToMujoco.message;
      if (!mjcfToMujoco.passed) {
        report.status = report.status === 'pass' ? 'partial' : report.status;
        report.failures.push(`MJCF mujoco parse failed: ${mjcfToMujoco.message}`);
      }
    } catch (error) {
      report.status = report.status === 'pass' ? 'partial' : report.status;
      report.mjcf.mujocoPyPassed = false;
      report.mjcf.mujocoPyMessage = String(error);
      report.failures.push(`MJCF mujoco command failed: ${String(error)}`);
    }
    await yieldToEventLoop();
    recordUnhandledRejectionFailures('Mujoco check', report);
  }

  await yieldToEventLoop();
  recordUnhandledRejectionFailures('post-processing', report);

  if (report.failures.length > 0 && report.status === 'pass') {
    report.status = 'partial';
  }
  return report;
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  if (options.groupSize < 1) {
    fail('group-size must be >= 1');
  }
  installDomGlobals();

  const rows = await buildFixtureMatrix({
    datasets: options.datasets,
    matches: options.matches,
    limit: options.limit,
  });
  const candidates = rows.filter(
    (entry) =>
      entry.actualStatus === 'ready' &&
      entry.format !== 'usd' &&
      entry.format !== 'mesh' &&
      entry.status !== 'classification_only',
  );

  if (candidates.length === 0) {
    fail('No ready source fixtures were found with the provided filters');
  }

  const selected = options.limit === null ? candidates : candidates.slice(0, options.limit);
  const contextCache = new Map<string, SourceContext>();
  for (const summary of selected) {
    const key = `${summary.dataset}::${summary.supportRoot || '.'}`;
    if (contextCache.has(key)) {
      continue;
    }
    const datasetRoot = toDatasetRoot(summary.dataset);
    const supportRootAbs = path.resolve(datasetRoot, summary.supportRoot || '.');
    if (!fs.existsSync(supportRootAbs)) {
      throw new Error(`Support root not found: ${supportRootAbs}`);
    }
    contextCache.set(
      key,
      await buildSourceContext(summary.dataset, supportRootAbs, datasetRoot),
    );
  }

  const groups = chunkArray(selected, options.groupSize);
  await fsPromises.mkdir(options.artifactsDir, { recursive: true });
  const groupsReport: GroupReport[] = [];

  for (let groupIndex = 0; groupIndex < groups.length; groupIndex += 1) {
    const group = groups[groupIndex];
    if (group.length === 0) {
      continue;
    }
    process.stdout.write(`\n[${groupIndex + 1}/${groups.length}] assembling ${group.length} model(s)\n`);
    groupsReport.push(await buildAssemblyForGroup(group, contextCache, options, groupIndex));
  }

  const summary = groupsReport.reduce(
    (acc, report) => {
      if (report.status === 'pass') {
        acc.pass += 1;
      } else if (report.status === 'partial') {
        acc.partial += 1;
      } else {
        acc.fail += 1;
      }
      return acc;
    },
    { pass: 0, partial: 0, fail: 0 },
  );

  const finalReport: FinalReport = {
    startedAt: new Date().toISOString(),
    finishedAt: '',
    options,
    groups: groupsReport.length,
    groupSize: options.groupSize,
    summary: {
      ...summary,
      candidateFixtures: selected.length,
    },
    groupsReport,
  };
  finalReport.finishedAt = new Date().toISOString();

  await writeTextFile(options.outputPath, JSON.stringify(finalReport, null, 2));
  process.stdout.write(`\nWrote report: ${options.outputPath}\n`);
  process.stdout.write(
    `Summary: pass=${finalReport.summary.pass} partial=${finalReport.summary.partial} fail=${finalReport.summary.fail}\n`,
  );
}

main().catch((error) => {
  process.stderr.write(`validation failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});

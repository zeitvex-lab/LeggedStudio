import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

import * as THREE from 'three';

import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { getCollisionGeometryEntries, getVisualGeometryEntries } from '@/core/robot';
import { createOriginMatrix } from '@/core/robot/kinematics';
import {
  GeometryType,
  JointType,
  type RobotData,
  type RobotFile,
  type UrdfJoint,
  type UrdfOrigin,
  type UrdfVisual,
} from '@/types';

import { installDomGlobals } from './importFixtureMatrixShared';

type SectionName = 'visual' | 'collision';
type Tuple3 = [number, number, number];
type QuatWxyz = [number, number, number, number];

interface Options {
  datasetRoot: string;
  limit: number | null;
  matches: string[];
  mujocoPython: string;
  mujocoTimeoutMs: number;
  outputPath: string;
  positionTolerance: number;
  rotationTolerance: number;
  scaleTolerance: number;
  requireVisual: boolean;
}

interface DatasetFile {
  absolutePath: string;
  relativePath: string;
}

interface CommandResult {
  code: number | null;
  stderr: string;
  stdout: string;
}

interface PoseFact {
  pos: Tuple3;
  quatWxyz: QuatWxyz;
}

export interface GeometryFact extends PoseFact {
  dimensions: Tuple3;
  index: number;
  linkName: string;
  meshPath?: string;
  name?: string;
  section: SectionName;
  type: string;
}

interface JointFact extends PoseFact {
  axis?: Tuple3;
  childName: string;
  limit?: { lower: number; upper: number };
  name: string;
  parentName: string;
  type: JointType;
}

interface StudioFacts {
  collisions: GeometryFact[];
  error: string | null;
  joints: JointFact[];
  linkCount: number | null;
  relativePath: string;
  status: 'ready' | 'error';
  visuals: GeometryFact[];
}

interface MujocoBodyFact extends PoseFact {
  id: number;
  name: string | null;
  parentId: number;
  parentName: string | null;
}

interface MujocoJointFact {
  axis: Tuple3;
  bodyName: string | null;
  id: number;
  limited: boolean;
  name: string | null;
  pos: Tuple3;
  range: [number, number];
  type: string;
}

export interface MujocoGeomFact extends PoseFact {
  bodyName: string | null;
  conaffinity: number;
  contype: number;
  dimensions: Tuple3;
  group: number;
  id: number;
  meshId: number | null;
  meshName: string | null;
  meshPos?: Tuple3 | null;
  meshQuatWxyz?: QuatWxyz | null;
  name: string | null;
  section: SectionName;
  size: Tuple3;
  type: string;
}

interface MujocoCompileResult {
  bodies: MujocoBodyFact[];
  counts: {
    nbody: number;
    ngeom: number;
    njnt: number;
    nmesh: number;
    nq: number;
    nu: number;
    nv: number;
  } | null;
  error: string | null;
  geoms: MujocoGeomFact[];
  joints: MujocoJointFact[];
  mode: 'collision' | 'visual';
  ok: boolean;
}

interface MujocoFileTruth {
  collision: MujocoCompileResult;
  relativePath: string;
  sourcePath: string;
  visual: MujocoCompileResult;
}

interface MujocoTruthReport {
  assetCount: number;
  datasetRoot: string;
  generatedAt: string;
  mujocoVersion: string;
  results: MujocoFileTruth[];
}

type IssueSeverity = 'hard' | 'skip';

export interface ValidationIssue {
  actual?: unknown;
  expected?: unknown;
  kind: string;
  message: string;
  severity: IssueSeverity;
}

interface FileValidationResult {
  issues: ValidationIssue[];
  mujoco: {
    collisionOk: boolean;
    collisionError: string | null;
    visualOk: boolean;
    visualError: string | null;
  };
  relativePath: string;
  resultStatus: 'pass' | 'fail' | 'skipped';
  studio: {
    collisionCount: number | null;
    error: string | null;
    jointCount: number | null;
    linkCount: number | null;
    status: StudioFacts['status'];
    visualCount: number | null;
  };
}

interface ValidationReport {
  datasetRoot: string;
  generatedAt: string;
  hardFailureCount: number;
  mujoco: {
    assetCount: number;
    version: string;
  };
  options: Pick<
    Options,
    'limit' | 'matches' | 'positionTolerance' | 'rotationTolerance' | 'scaleTolerance' | 'requireVisual'
  >;
  passCount: number;
  results: FileValidationResult[];
  selectedCount: number;
  skippedCount: number;
}

interface CompareOptions {
  positionTolerance: number;
  rotationTolerance: number;
  scaleTolerance: number;
}

interface MujocoTempPaths {
  manifestPath: string;
  truthPath: string;
}

const DEFAULT_DATASET_ROOT = path.resolve('test/urdf_files_dataset');
const DEFAULT_MUJOCO_PYTHON = process.env.MUJOCO_PYTHON || 'python3';
const DEFAULT_MUJOCO_TIMEOUT_MS = 1_200_000;
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/urdf-files-mujoco-truth.json');
const DEFAULT_POSITION_TOLERANCE = 1e-6;
const DEFAULT_ROTATION_TOLERANCE = 1e-6;
const DEFAULT_SCALE_TOLERANCE = 1e-6;
const HELPER_PATH = path.resolve('scripts/test/truth/inspect_urdf_mujoco_truth.py');
const TEXT_FILE_EXTENSIONS = new Set(['.dae', '.mtl', '.obj', '.urdf', '.xml']);
const ASSET_EXTENSIONS = new Set([
  '.dae',
  '.glb',
  '.gltf',
  '.jpg',
  '.jpeg',
  '.mtl',
  '.obj',
  '.png',
  '.stl',
  '.tif',
  '.tiff',
  '.urdf',
  '.xml',
]);

function fail(message: string): never {
  throw new Error(message);
}

function parsePositiveInteger(value: string, label: string): number {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isInteger(parsed) || parsed < 1) {
    fail(`Invalid ${label}: ${value}`);
  }
  return parsed;
}

function parseNonNegativeNumber(value: string, label: string): number {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed) || parsed < 0) {
    fail(`Invalid ${label}: ${value}`);
  }
  return parsed;
}

function printUsage(): void {
  process.stdout.write(`Usage:
  npx tsx -r tsconfig-paths/register scripts/test/truth/validate_urdf_files_dataset_against_mujoco.ts [options]

Options:
  --dataset-root <path>       Dataset root. Default: ${DEFAULT_DATASET_ROOT}
  --output <path>             JSON report path. Default: ${DEFAULT_OUTPUT_PATH}
  --match <token>             Repeatable filter against relative path.
  --limit <n>                 Limit selected URDF files after filtering.
  --mujoco-python <path>      Python executable with mujoco. Default: ${DEFAULT_MUJOCO_PYTHON}
  --mujoco-timeout-ms <n>     MuJoCo truth helper timeout. Default: ${DEFAULT_MUJOCO_TIMEOUT_MS}
  --position-tolerance <n>    Translation tolerance. Default: ${DEFAULT_POSITION_TOLERANCE}
  --rotation-tolerance <n>    Quaternion angular tolerance in radians. Default: ${DEFAULT_ROTATION_TOLERANCE}
  --scale-tolerance <n>       Dimension/scale tolerance. Default: ${DEFAULT_SCALE_TOLERANCE}
  --require-visual            Fail when MuJoCo visual-mode compile fails for a selected file.
  --help                      Show this help.
`);
}

function parseArgs(argv: string[]): Options {
  const options: Options = {
    datasetRoot: DEFAULT_DATASET_ROOT,
    limit: null,
    matches: [],
    mujocoPython: DEFAULT_MUJOCO_PYTHON,
    mujocoTimeoutMs: DEFAULT_MUJOCO_TIMEOUT_MS,
    outputPath: DEFAULT_OUTPUT_PATH,
    positionTolerance: DEFAULT_POSITION_TOLERANCE,
    rotationTolerance: DEFAULT_ROTATION_TOLERANCE,
    scaleTolerance: DEFAULT_SCALE_TOLERANCE,
    requireVisual: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const nextValue = () => {
      const value = argv[index + 1];
      if (!value) {
        fail(`Missing value for ${arg}`);
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
      case '--model':
        options.matches.push(nextValue().trim().toLowerCase());
        break;
      case '--limit':
        options.limit = parsePositiveInteger(nextValue(), '--limit');
        break;
      case '--mujoco-python':
        options.mujocoPython = nextValue();
        break;
      case '--mujoco-timeout-ms':
        options.mujocoTimeoutMs = parsePositiveInteger(nextValue(), '--mujoco-timeout-ms');
        break;
      case '--position-tolerance':
        options.positionTolerance = parseNonNegativeNumber(nextValue(), '--position-tolerance');
        break;
      case '--rotation-tolerance':
        options.rotationTolerance = parseNonNegativeNumber(nextValue(), '--rotation-tolerance');
        break;
      case '--scale-tolerance':
        options.scaleTolerance = parseNonNegativeNumber(nextValue(), '--scale-tolerance');
        break;
      case '--require-visual':
        options.requireVisual = true;
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

function toPosixPath(value: string): string {
  return value.replace(/\\/g, '/');
}

async function pathExists(targetPath: string): Promise<boolean> {
  try {
    await fs.access(targetPath);
    return true;
  } catch {
    return false;
  }
}

async function resolveDatasetRoot(inputRoot: string): Promise<string> {
  const urdfFilesRoot = path.join(inputRoot, 'urdf_files');
  return (await pathExists(urdfFilesRoot)) ? inputRoot : inputRoot;
}

async function collectFiles(rootDir: string): Promise<DatasetFile[]> {
  const results: DatasetFile[] = [];

  async function visit(currentDir: string): Promise<void> {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      if (entry.name === '.git') {
        continue;
      }
      const absolutePath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await visit(absolutePath);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      results.push({
        absolutePath,
        relativePath: toPosixPath(path.relative(rootDir, absolutePath)),
      });
    }
  }

  await visit(rootDir);
  return results.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
}

function selectUrdfFiles(files: DatasetFile[], options: Options): DatasetFile[] {
  const urdfFiles = files.filter((file) => path.extname(file.relativePath).toLowerCase() === '.urdf');
  const filtered = options.matches.length
    ? urdfFiles.filter((file) => {
        const haystack = file.relativePath.toLowerCase();
        return options.matches.every((match) => haystack.includes(match));
      })
    : urdfFiles;
  return options.limit == null ? filtered : filtered.slice(0, options.limit);
}

function robotFormatForPath(filePath: string): RobotFile['format'] {
  return path.extname(filePath).toLowerCase() === '.urdf' ? 'urdf' : 'asset';
}

async function buildAvailableFiles(files: DatasetFile[]): Promise<RobotFile[]> {
  return files
    .filter((file) => ASSET_EXTENSIONS.has(path.extname(file.relativePath).toLowerCase()))
    .map((file) => ({
      name: file.relativePath,
      content: '',
      format: robotFormatForPath(file.relativePath),
    }));
}

async function readTextFileIfUseful(file: DatasetFile): Promise<[string, string] | null> {
  const extension = path.extname(file.relativePath).toLowerCase();
  if (!TEXT_FILE_EXTENSIONS.has(extension)) {
    return null;
  }
  try {
    return [file.relativePath, await fs.readFile(file.absolutePath, 'utf8')];
  } catch {
    return null;
  }
}

async function buildTextFileContents(files: DatasetFile[]): Promise<Record<string, string>> {
  const entries = await Promise.all(files.map((file) => readTextFileIfUseful(file)));
  return Object.fromEntries(entries.filter((entry): entry is [string, string] => Boolean(entry)));
}

function tuple3FromVector(value?: { x?: number; y?: number; z?: number }): Tuple3 {
  return [value?.x ?? 0, value?.y ?? 0, value?.z ?? 0];
}

function tuple3FromUnknown(value: unknown): Tuple3 {
  if (!Array.isArray(value)) return [0, 0, 0];
  return [Number(value[0] ?? 0), Number(value[1] ?? 0), Number(value[2] ?? 0)];
}

function quatWxyzFromUnknown(value: unknown): QuatWxyz {
  if (!Array.isArray(value)) return [1, 0, 0, 0];
  return [Number(value[0] ?? 1), Number(value[1] ?? 0), Number(value[2] ?? 0), Number(value[3] ?? 0)];
}

function normalizeQuatWxyz(value: QuatWxyz): QuatWxyz {
  const length = Math.hypot(value[0], value[1], value[2], value[3]);
  if (length <= 1e-12) {
    return [1, 0, 0, 0];
  }
  return [value[0] / length, value[1] / length, value[2] / length, value[3] / length];
}

function poseFromOrigin(origin: UrdfOrigin | undefined): PoseFact {
  const matrix = createOriginMatrix(origin);
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  return {
    pos: [position.x, position.y, position.z],
    quatWxyz: normalizeQuatWxyz([quaternion.w, quaternion.x, quaternion.y, quaternion.z]),
  };
}

function geometryTypeLabel(type: GeometryType): string {
  return type;
}

function geometryDimensions(geometry: Pick<UrdfVisual, 'dimensions'>): Tuple3 {
  return tuple3FromVector(geometry.dimensions);
}

function geometryFact(
  linkName: string,
  section: SectionName,
  index: number,
  geometry: UrdfVisual,
): GeometryFact {
  const pose = poseFromOrigin(geometry.origin);
  return {
    ...pose,
    dimensions: geometryDimensions(geometry),
    index,
    linkName,
    meshPath: geometry.meshPath,
    name: geometry.name,
    section,
    type: geometryTypeLabel(geometry.type),
  };
}

function finiteLimitValue(value: number | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function jointFact(joint: UrdfJoint): JointFact {
  const pose = poseFromOrigin(joint.origin);
  return {
    ...pose,
    axis: joint.axis ? tuple3FromVector(joint.axis) : undefined,
    childName: joint.childLinkId,
    limit:
      finiteLimitValue(joint.limit?.lower) && finiteLimitValue(joint.limit?.upper)
        ? { lower: joint.limit.lower, upper: joint.limit.upper }
        : undefined,
    name: joint.name || joint.id,
    parentName: joint.parentLinkId,
    type: joint.type,
  };
}

function collectStudioFacts(relativePath: string, robot: RobotData): StudioFacts {
  const visuals: GeometryFact[] = [];
  const collisions: GeometryFact[] = [];

  Object.values(robot.links).forEach((link) => {
    getVisualGeometryEntries(link).forEach((entry) => {
      visuals.push(geometryFact(link.name || link.id, 'visual', entry.objectIndex, entry.geometry));
    });
    getCollisionGeometryEntries(link).forEach((entry) => {
      collisions.push(geometryFact(link.name || link.id, 'collision', entry.objectIndex, entry.geometry));
    });
  });

  return {
    collisions,
    error: null,
    joints: Object.values(robot.joints).map(jointFact),
    linkCount: Object.keys(robot.links).length,
    relativePath,
    status: 'ready',
    visuals,
  };
}

async function importStudioFacts(
  file: DatasetFile,
  availableFiles: RobotFile[],
  allFileContents: Record<string, string>,
): Promise<StudioFacts> {
  const content = allFileContents[file.relativePath] ?? (await fs.readFile(file.absolutePath, 'utf8'));
  const result = resolveRobotFileData(
    {
      name: file.relativePath,
      content,
      format: 'urdf',
    },
    {
      availableFiles,
      allFileContents,
    },
  );

  if (result.status !== 'ready') {
    return {
      collisions: [],
      error: result.status === 'error' ? result.message || result.reason : result.status,
      joints: [],
      linkCount: null,
      relativePath: file.relativePath,
      status: 'error',
      visuals: [],
    };
  }

  return collectStudioFacts(file.relativePath, result.robotData);
}

function runCommand(command: string, args: string[], timeoutMs = 300_000): Promise<CommandResult> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: process.cwd(),
      env: process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill('SIGTERM');
      resolve({
        code: null,
        stdout: Buffer.concat(stdoutChunks).toString('utf8'),
        stderr: `timed out after ${timeoutMs}ms\n${Buffer.concat(stderrChunks).toString('utf8')}`,
      });
    }, timeoutMs);

    child.stdout.on('data', (chunk) => stdoutChunks.push(Buffer.from(chunk)));
    child.stderr.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        code: null,
        stdout: Buffer.concat(stdoutChunks).toString('utf8'),
        stderr: error.message,
      });
    });
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({
        code,
        stdout: Buffer.concat(stdoutChunks).toString('utf8'),
        stderr: Buffer.concat(stderrChunks).toString('utf8'),
      });
    });
  });
}

async function writeMujocoManifest(
  datasetRoot: string,
  selectedFiles: DatasetFile[],
  allFiles: DatasetFile[],
  tempPaths: MujocoTempPaths,
): Promise<void> {
  const manifest = {
    generatedAt: new Date().toISOString(),
    datasetRoot,
    files: selectedFiles.map((file) => ({
      relativePath: file.relativePath,
      sourcePath: file.absolutePath,
    })),
    assetPaths: allFiles
      .filter((file) => ASSET_EXTENSIONS.has(path.extname(file.relativePath).toLowerCase()))
      .map((file) => file.relativePath),
  };
  await fs.mkdir(path.dirname(tempPaths.manifestPath), { recursive: true });
  await fs.writeFile(tempPaths.manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
}

async function runMujocoTruth(options: Options, tempPaths: MujocoTempPaths): Promise<MujocoTruthReport> {
  const result = await runCommand(options.mujocoPython, [
    HELPER_PATH,
    '--manifest',
    tempPaths.manifestPath,
    '--output',
    tempPaths.truthPath,
  ], options.mujocoTimeoutMs);

  if (result.code !== 0) {
    fail(`MuJoCo truth helper failed.\n${result.stderr || result.stdout}`);
  }

  const rawReport = JSON.parse(await fs.readFile(tempPaths.truthPath, 'utf8')) as MujocoTruthReport;
  return {
    ...rawReport,
    results: rawReport.results.map((entry) => ({
      ...entry,
      collision: normalizeCompileResult(entry.collision),
      visual: normalizeCompileResult(entry.visual),
    })),
  };
}

function createMujocoTempPaths(outputPath: string): MujocoTempPaths {
  const outputDir = path.dirname(outputPath);
  const outputExt = path.extname(outputPath);
  const outputStem = path.basename(outputPath, outputExt).replace(/[^A-Za-z0-9_.-]+/g, '-');
  const runId = `${outputStem || 'urdf-files-mujoco'}-${process.pid}-${Date.now()}`;
  return {
    manifestPath: path.join(outputDir, `${runId}.manifest.json`),
    truthPath: path.join(outputDir, `${runId}.raw-truth.json`),
  };
}

async function cleanupMujocoTempPaths(tempPaths: MujocoTempPaths): Promise<void> {
  await Promise.allSettled([fs.unlink(tempPaths.manifestPath), fs.unlink(tempPaths.truthPath)]);
}

function normalizeCompileResult(result: MujocoCompileResult): MujocoCompileResult {
  return {
    ...result,
    bodies: result.bodies.map((body) => ({
      ...body,
      pos: tuple3FromUnknown(body.pos),
      quatWxyz: normalizeQuatWxyz(quatWxyzFromUnknown(body.quatWxyz)),
    })),
    geoms: result.geoms.map((geom) => ({
      ...geom,
      dimensions: tuple3FromUnknown(geom.dimensions),
      meshPos: geom.meshPos ? tuple3FromUnknown(geom.meshPos) : null,
      meshQuatWxyz: geom.meshQuatWxyz ? normalizeQuatWxyz(quatWxyzFromUnknown(geom.meshQuatWxyz)) : null,
      pos: tuple3FromUnknown(geom.pos),
      quatWxyz: normalizeQuatWxyz(quatWxyzFromUnknown(geom.quatWxyz)),
      size: tuple3FromUnknown(geom.size),
    })),
    joints: result.joints.map((joint) => ({
      ...joint,
      axis: tuple3FromUnknown(joint.axis),
      pos: tuple3FromUnknown(joint.pos),
      range: [Number(joint.range[0] ?? 0), Number(joint.range[1] ?? 0)],
    })),
  };
}

function vectorMaxAbsDiff(left: Tuple3, right: Tuple3): number {
  return Math.max(
    Math.abs(left[0] - right[0]),
    Math.abs(left[1] - right[1]),
    Math.abs(left[2] - right[2]),
  );
}

function quaternionAngleDiff(left: QuatWxyz, right: QuatWxyz): number {
  const leftQuat = normalizeQuatWxyz(left);
  const rightQuat = normalizeQuatWxyz(right);
  const dot = Math.abs(
    leftQuat[0] * rightQuat[0] +
      leftQuat[1] * rightQuat[1] +
      leftQuat[2] * rightQuat[2] +
      leftQuat[3] * rightQuat[3],
  );
  return 2 * Math.acos(Math.min(1, Math.max(-1, dot)));
}

function matrixFromPose(pos: Tuple3, quatWxyz: QuatWxyz): THREE.Matrix4 {
  const quaternion = new THREE.Quaternion(quatWxyz[1], quatWxyz[2], quatWxyz[3], quatWxyz[0]).normalize();
  return new THREE.Matrix4().compose(
    new THREE.Vector3(pos[0], pos[1], pos[2]),
    quaternion,
    new THREE.Vector3(1, 1, 1),
  );
}

function decomposePose(matrix: THREE.Matrix4): PoseFact {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  return {
    pos: [position.x, position.y, position.z],
    quatWxyz: normalizeQuatWxyz([quaternion.w, quaternion.x, quaternion.y, quaternion.z]),
  };
}

function authoredTruthPose(geom: MujocoGeomFact): PoseFact {
  if (geom.type !== 'mesh' || !geom.meshPos || !geom.meshQuatWxyz) {
    return {
      pos: geom.pos,
      quatWxyz: geom.quatWxyz,
    };
  }

  const geomMatrix = matrixFromPose(geom.pos, geom.quatWxyz);
  const meshMatrix = matrixFromPose(geom.meshPos, geom.meshQuatWxyz);
  return decomposePose(geomMatrix.multiply(meshMatrix.invert()));
}

function geomTypeCompatible(studioType: string, truthType: string): boolean {
  if (studioType === truthType) {
    return true;
  }
  return studioType === GeometryType.MESH && truthType === 'mesh';
}

function geometryMatches(studio: GeometryFact, truth: MujocoGeomFact, options: CompareOptions): boolean {
  const truthPose = authoredTruthPose(truth);
  return (
    studio.linkName === truth.bodyName &&
    geomTypeCompatible(studio.type, truth.type) &&
    vectorMaxAbsDiff(studio.pos, truthPose.pos) <= options.positionTolerance &&
    vectorMaxAbsDiff(studio.dimensions, truth.dimensions) <= options.scaleTolerance &&
    quaternionAngleDiff(studio.quatWxyz, truthPose.quatWxyz) <= options.rotationTolerance
  );
}

function groupGeomsByBody(geoms: MujocoGeomFact[], section: SectionName): Map<string, MujocoGeomFact[]> {
  const grouped = new Map<string, MujocoGeomFact[]>();
  geoms
    .filter((geom) => geom.section === section && geom.bodyName)
    .forEach((geom) => {
      const key = geom.bodyName!;
      const entries = grouped.get(key) || [];
      entries.push(geom);
      grouped.set(key, entries);
    });
  return grouped;
}

export function compareGeometrySection(
  studioGeoms: GeometryFact[],
  truthGeoms: MujocoGeomFact[],
  section: SectionName,
  options: CompareOptions,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const truthByBody = groupGeomsByBody(truthGeoms, section);
  const studioByBody = new Map<string, GeometryFact[]>();
  studioGeoms.forEach((geom) => {
    const entries = studioByBody.get(geom.linkName) || [];
    entries.push(geom);
    studioByBody.set(geom.linkName, entries);
  });

  const linkNames = new Set([...studioByBody.keys(), ...truthByBody.keys()]);
  for (const linkName of linkNames) {
    const studioEntries = studioByBody.get(linkName) || [];
    const truthEntries = truthByBody.get(linkName) || [];
    if (studioEntries.length !== truthEntries.length) {
      issues.push({
        kind: `${section}_count_mismatch`,
        severity: 'hard',
        message: `${section} count mismatch on ${linkName}: MuJoCo=${truthEntries.length}, URDF Studio=${studioEntries.length}`,
        expected: truthEntries.length,
        actual: studioEntries.length,
      });
    }

    const compareCount = Math.min(studioEntries.length, truthEntries.length);
    for (let index = 0; index < compareCount; index += 1) {
      const studio = studioEntries[index];
      const truth = truthEntries[index];
      if (!geomTypeCompatible(studio.type, truth.type)) {
        issues.push({
          kind: `${section}_type_mismatch`,
          severity: 'hard',
          message: `${section} type mismatch on ${linkName}#${index}: MuJoCo=${truth.type}, URDF Studio=${studio.type}`,
          expected: truth.type,
          actual: studio.type,
        });
      }
      const truthPose = authoredTruthPose(truth);
      const positionError = vectorMaxAbsDiff(studio.pos, truthPose.pos);
      if (positionError > options.positionTolerance) {
        issues.push({
          kind: `${section}_xyz_mismatch`,
          severity: 'hard',
          message: `${section} xyz mismatch on ${linkName}#${index}: error=${positionError}`,
          expected: truthPose.pos,
          actual: studio.pos,
        });
      }
      const scaleError = vectorMaxAbsDiff(studio.dimensions, truth.dimensions);
      if (scaleError > options.scaleTolerance) {
        issues.push({
          kind: `${section}_scale_mismatch`,
          severity: 'hard',
          message: `${section} dimensions/scale mismatch on ${linkName}#${index}: error=${scaleError}`,
          expected: truth.dimensions,
          actual: studio.dimensions,
        });
      }
      const rotationError = quaternionAngleDiff(studio.quatWxyz, truthPose.quatWxyz);
      if (rotationError > options.rotationTolerance) {
        issues.push({
          kind: `${section}_rotation_mismatch`,
          severity: 'hard',
          message: `${section} rotation mismatch on ${linkName}#${index}: error=${rotationError}`,
          expected: truthPose.quatWxyz,
          actual: studio.quatWxyz,
        });
      }
    }
  }

  return issues;
}

function hasMatchingTruthGeom(
  studio: GeometryFact,
  truthGeoms: MujocoGeomFact[],
  section: SectionName,
  options: CompareOptions,
): boolean {
  return truthGeoms.some((truth) => truth.section === section && geometryMatches(studio, truth, options));
}

export function detectSectionMisclassifications(
  studioVisuals: GeometryFact[],
  studioCollisions: GeometryFact[],
  truthVisualGeoms: MujocoGeomFact[],
  truthCollisionGeoms: MujocoGeomFact[],
  options: CompareOptions,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  studioVisuals.forEach((studio) => {
    const inRightSection = hasMatchingTruthGeom(studio, truthVisualGeoms, 'visual', options);
    const inWrongSection = hasMatchingTruthGeom(studio, truthCollisionGeoms, 'collision', options);
    if (!inRightSection && inWrongSection) {
      issues.push({
        kind: 'section_mismatch',
        severity: 'hard',
        message: `visual geometry appears in MuJoCo collision section: ${studio.linkName}#${studio.index}`,
        expected: 'visual',
        actual: 'collision',
      });
    }
  });

  studioCollisions.forEach((studio) => {
    const inRightSection = hasMatchingTruthGeom(studio, truthCollisionGeoms, 'collision', options);
    const inWrongSection = hasMatchingTruthGeom(studio, truthVisualGeoms, 'visual', options);
    if (!inRightSection && inWrongSection) {
      issues.push({
        kind: 'section_mismatch',
        severity: 'hard',
        message: `collision geometry appears in MuJoCo visual section: ${studio.linkName}#${studio.index}`,
        expected: 'collision',
        actual: 'visual',
      });
    }
  });

  return issues;
}

function expectedMujocoJointType(type: JointType): string | null {
  if (type === JointType.REVOLUTE || type === JointType.CONTINUOUS) {
    return 'hinge';
  }
  if (type === JointType.PRISMATIC) {
    return 'slide';
  }
  if (type === JointType.BALL) {
    return 'ball';
  }
  if (type === JointType.FLOATING) {
    return 'free';
  }
  return null;
}

function compareJointFacts(studioJoints: JointFact[], truth: MujocoCompileResult, options: CompareOptions): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const bodiesByName = new Map(truth.bodies.filter((body) => body.name).map((body) => [body.name!, body]));
  const jointsByName = new Map(truth.joints.filter((joint) => joint.name).map((joint) => [joint.name!, joint]));
  const studioJointsByChild = new Map(studioJoints.map((joint) => [joint.childName, joint]));
  const studioJointsByName = new Map(studioJoints.map((joint) => [joint.name, joint]));

  truth.bodies.forEach((body) => {
    if (!body.name || body.parentId === 0) {
      return;
    }

    if (!studioJointsByChild.has(body.name)) {
      issues.push({
        kind: 'joint_missing_for_body',
        severity: 'hard',
        message: `URDF Studio joint missing for MuJoCo body ${body.name}`,
        expected: body.name,
        actual: null,
      });
    }
  });

  truth.joints.forEach((truthJoint) => {
    if (!truthJoint.name) {
      return;
    }

    if (!studioJointsByName.has(truthJoint.name)) {
      issues.push({
        kind: 'joint_missing_in_studio',
        severity: 'hard',
        message: `URDF Studio joint missing for MuJoCo joint ${truthJoint.name}`,
        expected: truthJoint.name,
        actual: null,
      });
    }
  });

  studioJoints.forEach((studio) => {
    const childBody = bodiesByName.get(studio.childName);
    if (!childBody) {
      issues.push({
        kind: 'joint_child_body_missing',
        severity: 'hard',
        message: `MuJoCo body missing for joint child ${studio.childName} (${studio.name})`,
      });
      return;
    }

    if (childBody.parentName !== studio.parentName) {
      issues.push({
        kind: 'joint_parent_mismatch',
        severity: 'hard',
        message: `joint parent mismatch for ${studio.name}: MuJoCo=${childBody.parentName}, URDF Studio=${studio.parentName}`,
        expected: childBody.parentName,
        actual: studio.parentName,
      });
    }

    const originError = vectorMaxAbsDiff(studio.pos, childBody.pos);
    if (originError > options.positionTolerance) {
      issues.push({
        kind: 'joint_origin_xyz_mismatch',
        severity: 'hard',
        message: `joint origin xyz mismatch for ${studio.name}: error=${originError}`,
        expected: childBody.pos,
        actual: studio.pos,
      });
    }

    const rotationError = quaternionAngleDiff(studio.quatWxyz, childBody.quatWxyz);
    if (rotationError > options.rotationTolerance) {
      issues.push({
        kind: 'joint_origin_rotation_mismatch',
        severity: 'hard',
        message: `joint origin rotation mismatch for ${studio.name}: error=${rotationError}`,
        expected: childBody.quatWxyz,
        actual: studio.quatWxyz,
      });
    }

    const expectedType = expectedMujocoJointType(studio.type);
    if (!expectedType) {
      return;
    }

    const truthJoint = jointsByName.get(studio.name);
    if (!truthJoint) {
      issues.push({
        kind: 'joint_missing',
        severity: 'hard',
        message: `MuJoCo joint missing for ${studio.name}`,
      });
      return;
    }

    if (truthJoint.type !== expectedType) {
      issues.push({
        kind: 'joint_type_mismatch',
        severity: 'hard',
        message: `joint type mismatch for ${studio.name}: MuJoCo=${truthJoint.type}, URDF Studio=${studio.type}`,
        expected: truthJoint.type,
        actual: studio.type,
      });
    }

    if (studio.axis) {
      const axisError = vectorMaxAbsDiff(studio.axis, truthJoint.axis);
      if (axisError > options.scaleTolerance) {
        issues.push({
          kind: 'joint_axis_mismatch',
          severity: 'hard',
          message: `joint axis mismatch for ${studio.name}: error=${axisError}`,
          expected: truthJoint.axis,
          actual: studio.axis,
        });
      }
    }

    if (studio.type !== JointType.CONTINUOUS && studio.limit && truthJoint.limited) {
      const lowerError = Math.abs(studio.limit.lower - truthJoint.range[0]);
      const upperError = Math.abs(studio.limit.upper - truthJoint.range[1]);
      if (lowerError > options.scaleTolerance || upperError > options.scaleTolerance) {
        issues.push({
          kind: 'joint_limit_mismatch',
          severity: 'hard',
          message: `joint limit mismatch for ${studio.name}: lowerError=${lowerError}, upperError=${upperError}`,
          expected: truthJoint.range,
          actual: [studio.limit.lower, studio.limit.upper],
        });
      }
    }
  });

  return issues;
}

export function hasComparableMujocoContent(truth: MujocoFileTruth): boolean {
  return [truth.collision, truth.visual].some((compileResult) => {
    if (!compileResult.ok || !compileResult.counts) {
      return false;
    }

    return (
      compileResult.counts.nbody > 1 ||
      compileResult.counts.ngeom > 0 ||
      compileResult.counts.njnt > 0
    );
  });
}

function validateFile(
  relativePath: string,
  studio: StudioFacts,
  truth: MujocoFileTruth,
  options: Options,
): FileValidationResult {
  const compareOptions: CompareOptions = {
    positionTolerance: options.positionTolerance,
    rotationTolerance: options.rotationTolerance,
    scaleTolerance: options.scaleTolerance,
  };
  const issues: ValidationIssue[] = [];
  const anyMujocoOk = truth.collision.ok || truth.visual.ok;
  const comparableMujocoContent = hasComparableMujocoContent(truth);

  if (!anyMujocoOk) {
    issues.push({
      kind: 'mujoco_compile_skipped',
      severity: 'skip',
      message: `MuJoCo could not compile this URDF. collision=${truth.collision.error}; visual=${truth.visual.error}`,
    });
  }

  if (studio.status !== 'ready') {
    const hasHardComparableFailure = anyMujocoOk && comparableMujocoContent;
    issues.push({
      kind: hasHardComparableFailure
        ? 'studio_import_failed'
        : comparableMujocoContent
          ? 'studio_import_skipped'
          : 'source_only_fragment_skipped',
      severity: hasHardComparableFailure ? 'hard' : 'skip',
      message: comparableMujocoContent
        ? studio.error || 'URDF Studio import failed'
        : 'URDF has no comparable MuJoCo bodies, geoms, or joints.',
    });
  }

  if (options.requireVisual && !truth.visual.ok) {
    issues.push({
      kind: 'mujoco_visual_compile_failed',
      severity: 'hard',
      message: truth.visual.error || 'MuJoCo visual-mode compile failed',
    });
  }

  if (studio.status === 'ready') {
    const kinematicTruth = truth.collision.ok ? truth.collision : truth.visual.ok ? truth.visual : null;
    if (kinematicTruth) {
      issues.push(...compareJointFacts(studio.joints, kinematicTruth, compareOptions));
    }

    if (truth.collision.ok) {
      issues.push(...compareGeometrySection(studio.collisions, truth.collision.geoms, 'collision', compareOptions));
    }

    if (truth.visual.ok) {
      issues.push(...compareGeometrySection(studio.visuals, truth.visual.geoms, 'visual', compareOptions));
      issues.push(
        ...detectSectionMisclassifications(
          studio.visuals,
          studio.collisions,
          truth.visual.geoms,
          truth.collision.ok ? truth.collision.geoms : [],
          compareOptions,
        ),
      );
    }
  }

  const hardIssues = issues.filter((issue) => issue.severity === 'hard');
  const skipped = issues.some((issue) => issue.severity === 'skip') && hardIssues.length === 0;

  return {
    issues,
    mujoco: {
      collisionOk: truth.collision.ok,
      collisionError: truth.collision.error,
      visualOk: truth.visual.ok,
      visualError: truth.visual.error,
    },
    relativePath,
    resultStatus: hardIssues.length ? 'fail' : skipped ? 'skipped' : 'pass',
    studio: {
      collisionCount: studio.status === 'ready' ? studio.collisions.length : null,
      error: studio.error,
      jointCount: studio.status === 'ready' ? studio.joints.length : null,
      linkCount: studio.linkCount,
      status: studio.status,
      visualCount: studio.status === 'ready' ? studio.visuals.length : null,
    },
  };
}

async function main(): Promise<void> {
  installDomGlobals();
  const options = parseArgs(process.argv.slice(2));
  const datasetRoot = await resolveDatasetRoot(options.datasetRoot);
  const allFiles = await collectFiles(datasetRoot);
  const selectedFiles = selectUrdfFiles(allFiles, options);
  if (selectedFiles.length === 0) {
    fail('No URDF files matched the requested filters.');
  }

  const [availableFiles, allFileContents] = await Promise.all([
    buildAvailableFiles(allFiles),
    buildTextFileContents(allFiles),
  ]);
  const tempPaths = createMujocoTempPaths(options.outputPath);
  await writeMujocoManifest(datasetRoot, selectedFiles, allFiles, tempPaths);
  const mujocoTruth = await runMujocoTruth(options, tempPaths);
  await cleanupMujocoTempPaths(tempPaths);
  const truthByPath = new Map(mujocoTruth.results.map((truth) => [truth.relativePath, truth]));

  const results: FileValidationResult[] = [];
  for (const file of selectedFiles) {
    const studioFacts = await importStudioFacts(file, availableFiles, allFileContents);
    const truth = truthByPath.get(file.relativePath);
    if (!truth) {
      results.push({
        issues: [
          {
            kind: 'mujoco_truth_missing',
            severity: 'hard',
            message: `MuJoCo truth missing for ${file.relativePath}`,
          },
        ],
        mujoco: {
          collisionOk: false,
          collisionError: 'missing',
          visualOk: false,
          visualError: 'missing',
        },
        relativePath: file.relativePath,
        resultStatus: 'fail',
        studio: {
          collisionCount: studioFacts.status === 'ready' ? studioFacts.collisions.length : null,
          error: studioFacts.error,
          jointCount: studioFacts.status === 'ready' ? studioFacts.joints.length : null,
          linkCount: studioFacts.linkCount,
          status: studioFacts.status,
          visualCount: studioFacts.status === 'ready' ? studioFacts.visuals.length : null,
        },
      });
      continue;
    }
    results.push(validateFile(file.relativePath, studioFacts, truth, options));
  }

  const hardFailureCount = results.reduce(
    (sum, result) => sum + result.issues.filter((issue) => issue.severity === 'hard').length,
    0,
  );
  const report: ValidationReport = {
    datasetRoot,
    generatedAt: new Date().toISOString(),
    hardFailureCount,
    mujoco: {
      assetCount: mujocoTruth.assetCount,
      version: mujocoTruth.mujocoVersion,
    },
    options: {
      limit: options.limit,
      matches: options.matches,
      positionTolerance: options.positionTolerance,
      rotationTolerance: options.rotationTolerance,
      scaleTolerance: options.scaleTolerance,
      requireVisual: options.requireVisual,
    },
    passCount: results.filter((result) => result.resultStatus === 'pass').length,
    results,
    selectedCount: selectedFiles.length,
    skippedCount: results.filter((result) => result.resultStatus === 'skipped').length,
  };

  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
  await fs.writeFile(options.outputPath, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

  console.log(
    JSON.stringify(
      {
        outputPath: options.outputPath,
        selectedCount: report.selectedCount,
        passCount: report.passCount,
        skippedCount: report.skippedCount,
        hardFailureCount: report.hardFailureCount,
        mujocoVersion: report.mujoco.version,
      },
      null,
      2,
    ),
  );

  if (hardFailureCount > 0) {
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : error);
    process.exitCode = 1;
  });
}

import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import { prepareImportPayload } from '@/app/utils/importPreparation';
import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { computeLinkWorldMatrices } from '@/core/robot';
import { GeometryType, type RobotData, type RobotFile, type UrdfJoint, type UrdfLink, type UrdfVisual } from '@/types';

const execFileAsync = promisify(execFile);

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;

type Vector3Like = { x: number; y: number; z: number };
type EulerLike = { r: number; p: number; y: number };
type Pose = { xyz: Vector3Like; rpy: EulerLike };

type TruthCollision = {
  name: string;
  type: string;
  localPose: Pose;
  worldPose: Pose;
};

type StaticTruthModel = {
  modelName: string;
  modelPose: Pose;
  links: Record<string, { name: string; collisions: TruthCollision[] }>;
};

type CliTruthLink = {
  name: string;
  worldPose: Pose;
};

type CliTruthJoint = {
  name: string;
  parent: string;
  child: string;
  childRelativePose: Pose;
  parentRelativePose: Pose;
};

type CliTruthModel = {
  modelName: string;
  links: Record<string, CliTruthLink>;
  joints: Record<string, CliTruthJoint>;
};

type PoseMismatch = {
  name: string;
  translationError: number;
  rotationError: number;
  expected: Pose;
  actual: Pose;
};

type CountMismatch = {
  name: string;
  expected: number;
  actual: number;
};

type TypeMismatch = {
  name: string;
  index: number;
  expected: string;
  actual: string;
};

type EndpointMismatch = {
  name: string;
  expectedParent: string;
  expectedChild: string;
  actualParent: string;
  actualChild: string;
};

type SampleReport = {
  sample: string;
  preferredFileName: string | null;
  importStatus: string;
  cliStatus: string;
  cliTruthCounts?: {
    links: number;
    joints: number;
    collisions: number;
  };
  importedCounts?: {
    links: number;
    joints: number;
    collisions: number;
    syntheticLinks: number;
    syntheticJoints: number;
  };
  missingLinks: string[];
  missingJoints: string[];
  linkPoseMismatches: PoseMismatch[];
  jointOriginMismatches: PoseMismatch[];
  jointEndpointMismatches: EndpointMismatch[];
  collisionCountMismatches: CountMismatch[];
  collisionPoseMismatches: PoseMismatch[];
  collisionTypeMismatches: TypeMismatch[];
  notes: string[];
};

const ZERO_VECTOR = { x: 0, y: 0, z: 0 };
const ZERO_EULER = { r: 0, p: 0, y: 0 };
const IDENTITY_POSE: Pose = { xyz: ZERO_VECTOR, rpy: ZERO_EULER };
const IDENTITY_SCALE = new THREE.Vector3(1, 1, 1);
const POSITION_TOLERANCE = 1e-5;
const ROTATION_TOLERANCE = 1e-4;
const WORLD_FRAME = 'world';
const SYNTHETIC_JOINT_STAGE_MARKER = '__joint_stage_';
const OUTPUT_DIR = path.resolve('tmp/sdf-cli-audit');

function isElementNode(node: Node | null | undefined): node is Element {
  return !!node && node.nodeType === 1;
}

function getDirectChildElements(parent: Element, tagName?: string): Element[] {
  return Array.from(parent.childNodes)
    .filter(isElementNode)
    .filter((child) => !tagName || child.tagName === tagName);
}

function getFirstDirectChild(parent: Element, tagName: string): Element | null {
  return getDirectChildElements(parent, tagName)[0] ?? null;
}

function parseNumberTuple(text: string | null | undefined): number[] {
  return (text ?? '')
    .trim()
    .split(/\s+/)
    .map((value) => Number.parseFloat(value))
    .filter((value) => Number.isFinite(value));
}

function parsePoseText(text: string | null | undefined): Pose {
  const [x = 0, y = 0, z = 0, r = 0, p = 0, yaw = 0] = parseNumberTuple(text);
  return {
    xyz: { x, y, z },
    rpy: { r, p, y: yaw },
  };
}

function poseToMatrix(pose: Pose): THREE.Matrix4 {
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3(pose.xyz.x, pose.xyz.y, pose.xyz.z);
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(pose.rpy.r, pose.rpy.p, pose.rpy.y, 'ZYX'),
  );
  matrix.compose(position, quaternion, IDENTITY_SCALE);
  return matrix;
}

function matrixToPose(matrix: THREE.Matrix4): Pose {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(position, quaternion, scale);
  const euler = new THREE.Euler(0, 0, 0, 'ZYX').setFromQuaternion(quaternion);

  return {
    xyz: { x: position.x, y: position.y, z: position.z },
    rpy: { r: euler.x, p: euler.y, y: euler.z },
  };
}

function poseDifference(expected: Pose, actual: Pose): { translationError: number; rotationError: number } {
  const dx = actual.xyz.x - expected.xyz.x;
  const dy = actual.xyz.y - expected.xyz.y;
  const dz = actual.xyz.z - expected.xyz.z;
  const translationError = Math.sqrt(dx * dx + dy * dy + dz * dz);

  const wrap = (angle: number) => {
    let current = angle;
    while (current > Math.PI) current -= Math.PI * 2;
    while (current < -Math.PI) current += Math.PI * 2;
    return current;
  };

  const rotationError = Math.max(
    Math.abs(wrap(actual.rpy.r - expected.rpy.r)),
    Math.abs(wrap(actual.rpy.p - expected.rpy.p)),
    Math.abs(wrap(actual.rpy.y - expected.rpy.y)),
  );

  return { translationError, rotationError };
}

function geometryTypeToLabel(type: GeometryType | undefined): string {
  if (!type) return 'none';
  return String(type).toLowerCase();
}

function parseTruthGeometryType(geometryEl: Element | null): string {
  if (!geometryEl) return 'none';
  if (getFirstDirectChild(geometryEl, 'box')) return 'box';
  if (getFirstDirectChild(geometryEl, 'cylinder')) return 'cylinder';
  if (getFirstDirectChild(geometryEl, 'sphere')) return 'sphere';
  if (getFirstDirectChild(geometryEl, 'capsule')) return 'capsule';
  if (getFirstDirectChild(geometryEl, 'mesh')) return 'mesh';
  return 'none';
}

function getImportedCollisionBodies(link: UrdfLink): UrdfVisual[] {
  const bodies: UrdfVisual[] = [];
  if (link.collision.type !== GeometryType.NONE) {
    bodies.push(link.collision);
  }
  return bodies.concat(link.collisionBodies || []);
}

function computeImportedWorldPoses(robotData: RobotData): Record<string, Pose> {
  const worldMatrices = computeLinkWorldMatrices(robotData);
  const result: Record<string, Pose> = {};
  Object.keys(robotData.links).forEach((linkId) => {
    const matrix = worldMatrices[linkId];
    result[linkId] = matrixToPose(matrix ?? new THREE.Matrix4().identity());
  });
  return result;
}

function isSyntheticJointStageLinkName(linkName: string): boolean {
  return linkName.includes(SYNTHETIC_JOINT_STAGE_MARKER);
}

function isSyntheticJointStageJoint(joint: UrdfJoint): boolean {
  return joint.id.endsWith('_fixed') && isSyntheticJointStageLinkName(joint.parentLinkId);
}

function buildAllFileContents(payload: Awaited<ReturnType<typeof prepareImportPayload>>): Record<string, string> {
  return {
    ...Object.fromEntries(payload.robotFiles.filter((file) => file.content).map((file) => [file.name, file.content])),
    ...Object.fromEntries(payload.textFiles.map((file) => [file.path, file.content])),
  };
}

function parseStaticTruthModel(sourcePath: string, xmlString: string): StaticTruthModel {
  const doc = new DOMParser().parseFromString(xmlString.trim(), 'text/xml');
  if (doc.querySelector('parsererror')) {
    throw new Error(`Failed to parse XML for ${sourcePath}`);
  }

  const modelEl = doc.querySelector('sdf > model, model');
  if (!modelEl) {
    throw new Error(`No <model> found in ${sourcePath}`);
  }

  const modelName = modelEl.getAttribute('name')?.trim() || path.basename(sourcePath, '.sdf');
  const modelPose = parsePoseText(getFirstDirectChild(modelEl, 'pose')?.textContent);

  const links: Record<string, { name: string; collisions: TruthCollision[] }> = {};
  getDirectChildElements(modelEl, 'link').forEach((linkEl) => {
    const linkName = linkEl.getAttribute('name')?.trim();
    if (!linkName) return;

    const collisions = getDirectChildElements(linkEl, 'collision').map((collisionEl, index): TruthCollision => {
      const localPose = parsePoseText(getFirstDirectChild(collisionEl, 'pose')?.textContent);
      return {
        name: collisionEl.getAttribute('name')?.trim() || `${linkName}_collision_${index}`,
        type: parseTruthGeometryType(getFirstDirectChild(collisionEl, 'geometry')),
        localPose,
        worldPose: localPose,
      };
    });

    links[linkName] = { name: linkName, collisions };
  });

  return { modelName, modelPose, links };
}

function sanitizeName(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, '_');
}

async function runIgn(args: string[], options?: { cwd?: string; timeoutMs?: number }): Promise<{ stdout: string; stderr: string }> {
  const { stdout, stderr } = await execFileAsync('ign', args, {
    cwd: options?.cwd,
    timeout: options?.timeoutMs ?? 30_000,
    maxBuffer: 32 * 1024 * 1024,
  });
  return {
    stdout: String(stdout),
    stderr: String(stderr),
  };
}

async function unzipSample(sampleZipPath: string, destinationDir: string): Promise<void> {
  await fs.rm(destinationDir, { recursive: true, force: true });
  await fs.mkdir(destinationDir, { recursive: true });
  await execFileAsync('unzip', ['-oq', sampleZipPath, '-d', destinationDir], {
    maxBuffer: 16 * 1024 * 1024,
  });
}

async function findExtractedPreferredFile(destinationDir: string, preferredFileName: string): Promise<string> {
  const directCandidate = path.join(destinationDir, preferredFileName);
  try {
    const stat = await fs.stat(directCandidate);
    if (stat.isFile()) {
      return directCandidate;
    }
  } catch {
    // fall through to recursive search
  }

  const candidates: string[] = [];
  const normalizedPreferred = preferredFileName.split(/[\\/]+/).join(path.sep);

  async function walk(currentDir: string): Promise<void> {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }
      if (fullPath.endsWith(`${path.sep}${normalizedPreferred}`) || entry.name === path.basename(normalizedPreferred)) {
        candidates.push(fullPath);
      }
    }
  }

  await walk(destinationDir);
  if (candidates.length === 1) {
    return candidates[0];
  }
  if (candidates.length > 1) {
    const exact = candidates.find((candidate) => candidate.endsWith(`${path.sep}${preferredFileName}`));
    if (exact) return exact;
  }
  throw new Error(`Unable to locate preferred extracted file ${preferredFileName} under ${destinationDir}`);
}

async function buildCliTruthFiles(
  extractedPreferredFilePath: string,
  preferredFileName: string,
  sampleOutputDir: string,
): Promise<{
  printedSdf: string;
  poseGraph: string;
  frameGraph: string;
  checkOutput: string;
  worldPath: string;
  modelName: string;
  modelPose: Pose;
}> {
  const check = await runIgn(['sdf', '-k', extractedPreferredFilePath]);
  const printed = await runIgn(['sdf', '-p', extractedPreferredFilePath]);
  const poseGraph = await runIgn(['sdf', '-g', 'pose', extractedPreferredFilePath]);
  const frameGraph = await runIgn(['sdf', '-g', 'frame', extractedPreferredFilePath]);

  await fs.writeFile(path.join(sampleOutputDir, 'check.txt'), `${check.stdout}${check.stderr}`, 'utf8');
  await fs.writeFile(path.join(sampleOutputDir, 'printed.sdf'), printed.stdout, 'utf8');
  await fs.writeFile(path.join(sampleOutputDir, 'pose-graph.dot'), poseGraph.stdout, 'utf8');
  await fs.writeFile(path.join(sampleOutputDir, 'frame-graph.dot'), frameGraph.stdout, 'utf8');

  const printedDoc = new DOMParser().parseFromString(printed.stdout.trim(), 'text/xml');
  if (printedDoc.querySelector('parsererror')) {
    throw new Error(`CLI printed output could not be parsed for ${preferredFileName}`);
  }

  const modelEl = printedDoc.querySelector('sdf > model, model');
  if (!modelEl) {
    throw new Error(`CLI printed output did not contain a <model> for ${preferredFileName}`);
  }

  const modelName = modelEl.getAttribute('name')?.trim();
  if (!modelName) {
    throw new Error(`Printed model has no name for ${preferredFileName}`);
  }
  const modelPose = parsePoseText(getFirstDirectChild(modelEl, 'pose')?.textContent);

  const preferredDir = path.dirname(extractedPreferredFilePath);
  const worldPath = path.join(preferredDir, '__codex_cli_truth_world__.sdf');
  const worldSdf = [
    `<sdf version="1.9">`,
    `  <world name="default">`,
    modelEl.outerHTML.split('\n').map((line) => `    ${line}`).join('\n'),
    `  </world>`,
    `</sdf>`,
    '',
  ].join('\n');
  await fs.writeFile(worldPath, worldSdf, 'utf8');

  return {
    printedSdf: printed.stdout,
    poseGraph: poseGraph.stdout,
    frameGraph: frameGraph.stdout,
    checkOutput: `${check.stdout}${check.stderr}`.trim(),
    worldPath,
    modelName,
    modelPose,
  };
}

function parseBracketTriple(text: string): [number, number, number] {
  const values = parseNumberTuple(text.replace(/^\[/, '').replace(/\]$/, ''));
  const [a = 0, b = 0, c = 0] = values;
  return [a, b, c];
}

function parseCliLinks(stdout: string): Record<string, CliTruthLink> {
  const result: Record<string, CliTruthLink> = {};
  const lines = stdout.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? '';
    if (!line.startsWith('- Link [')) continue;

    let name = '';
    let pose: Pose | null = null;
    for (let j = i + 1; j < lines.length; j += 1) {
      const next = lines[j] ?? '';
      if (next.startsWith('- Link [')) {
        i = j - 1;
        break;
      }
      if (next.startsWith('  - Name: ')) {
        name = next.slice('  - Name: '.length).trim();
      }
      if (next.startsWith('  - Pose [ XYZ (m) ] [ RPY (rad) ]:')) {
        const xyzLine = (lines[j + 1] ?? '').trim();
        const rpyLine = (lines[j + 2] ?? '').trim();
        const [x, y, z] = parseBracketTriple(xyzLine);
        const [r, p, yaw] = parseBracketTriple(rpyLine);
        pose = {
          xyz: { x, y, z },
          rpy: { r, p, y: yaw },
        };
      }
      if (j === lines.length - 1) {
        i = j;
      }
    }

    if (name && pose) {
      result[name] = { name, worldPose: pose };
    }
  }
  return result;
}

function parseCliJoints(stdout: string, linkTruth: Record<string, CliTruthLink>): Record<string, CliTruthJoint> {
  const result: Record<string, CliTruthJoint> = {};
  const lines = stdout.split(/\r?\n/);
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? '';
    if (!line.startsWith('- Joint [')) continue;

    let name = '';
    let parent = '';
    let child = '';
    let childRelativePose: Pose | null = null;
    for (let j = i + 1; j < lines.length; j += 1) {
      const next = lines[j] ?? '';
      if (next.startsWith('- Joint [')) {
        i = j - 1;
        break;
      }
      if (next.startsWith('  - Name: ')) {
        name = next.slice('  - Name: '.length).trim();
      }
      if (next.startsWith('  - Parent Link: ')) {
        parent = next.slice('  - Parent Link: '.length).replace(/\s+\[\d+\]$/, '').trim();
      }
      if (next.startsWith('  - Child Link: ')) {
        child = next.slice('  - Child Link: '.length).replace(/\s+\[\d+\]$/, '').trim();
      }
      if (next.startsWith('  - Pose [ XYZ (m) ] [ RPY (rad) ]:')) {
        const xyzLine = (lines[j + 1] ?? '').trim();
        const rpyLine = (lines[j + 2] ?? '').trim();
        const [x, y, z] = parseBracketTriple(xyzLine);
        const [r, p, yaw] = parseBracketTriple(rpyLine);
        childRelativePose = {
          xyz: { x, y, z },
          rpy: { r, p, y: yaw },
        };
      }
      if (j === lines.length - 1) {
        i = j;
      }
    }

    if (!name || !childRelativePose || !child) {
      continue;
    }

    const childWorld = linkTruth[child]?.worldPose;
    if (!childWorld) {
      throw new Error(`CLI joint ${name} references missing child link ${child}`);
    }

    const childWorldMatrix = poseToMatrix(childWorld);
    const jointWorldMatrix = childWorldMatrix.clone().multiply(poseToMatrix(childRelativePose));
    const parentWorldMatrix = parent === WORLD_FRAME
      ? new THREE.Matrix4().identity()
      : poseToMatrix(linkTruth[parent]?.worldPose ?? IDENTITY_POSE);
    const parentRelativePose = matrixToPose(parentWorldMatrix.clone().invert().multiply(jointWorldMatrix));

    result[name] = {
      name,
      parent,
      child,
      childRelativePose,
      parentRelativePose,
    };
  }
  return result;
}

function applyModelPoseToCliLinks(
  links: Record<string, CliTruthLink>,
  modelPose: Pose,
): Record<string, CliTruthLink> {
  const modelMatrix = poseToMatrix(modelPose);
  return Object.fromEntries(
    Object.entries(links).map(([name, link]) => ([
      name,
      {
        ...link,
        worldPose: matrixToPose(modelMatrix.clone().multiply(poseToMatrix(link.worldPose))),
      },
    ])),
  );
}

function resolveSyntheticStageTerminalLinkId(linkId: string, robotData: RobotData): string {
  let currentLinkId = linkId;
  const visited = new Set<string>();

  while (currentLinkId && isSyntheticJointStageLinkName(currentLinkId) && !visited.has(currentLinkId)) {
    visited.add(currentLinkId);
    const passthroughJoint = Object.values(robotData.joints).find((joint) => (
      joint.parentLinkId === currentLinkId && joint.id.endsWith('_fixed')
    ));
    if (!passthroughJoint) {
      break;
    }
    currentLinkId = passthroughJoint.childLinkId;
  }

  return currentLinkId;
}

async function waitForModel(modelName: string, attempts = 60): Promise<string> {
  let lastStdout = '';
  let lastStderr = '';
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const { stdout, stderr } = await runIgn(['model', '--list'], { timeoutMs: 8_000 });
      lastStdout = stdout;
      lastStderr = stderr;
      if (stdout.includes(modelName)) {
        return stdout;
      }
    } catch (error) {
      lastStderr = String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  throw new Error(`Timed out waiting for model ${modelName}. Last stdout:\n${lastStdout}\nLast stderr:\n${lastStderr}`);
}

async function terminateProcess(child: ReturnType<typeof spawn>): Promise<void> {
  if (child.exitCode !== null) {
    return;
  }

  child.kill('SIGTERM');
  await Promise.race([
    new Promise((resolve) => child.once('exit', resolve)),
    new Promise((resolve) => setTimeout(resolve, 2_000)),
  ]);

  if (child.exitCode === null) {
    child.kill('SIGKILL');
    await Promise.race([
      new Promise((resolve) => child.once('exit', resolve)),
      new Promise((resolve) => setTimeout(resolve, 2_000)),
    ]);
  }
}

async function captureCliTruth(
  worldPath: string,
  modelName: string,
  modelPose: Pose,
  sampleOutputDir: string,
): Promise<CliTruthModel> {
  const serverLogPath = path.join(sampleOutputDir, 'gazebo-server.log');
  const server = spawn('ign', ['gazebo', '-s', worldPath], {
    cwd: path.dirname(worldPath),
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const stdoutChunks: Buffer[] = [];
  const stderrChunks: Buffer[] = [];
  server.stdout?.on('data', (chunk) => stdoutChunks.push(Buffer.from(chunk)));
  server.stderr?.on('data', (chunk) => stderrChunks.push(Buffer.from(chunk)));

  try {
    const modelList = await waitForModel(modelName);
    await fs.writeFile(path.join(sampleOutputDir, 'model-list.txt'), modelList, 'utf8');

    const linkResult = await runIgn(['model', '-m', modelName, '-l'], { timeoutMs: 20_000 });
    const jointResult = await runIgn(['model', '-m', modelName, '-j'], { timeoutMs: 20_000 });

    await fs.writeFile(path.join(sampleOutputDir, 'links.txt'), linkResult.stdout, 'utf8');
    await fs.writeFile(path.join(sampleOutputDir, 'joints.txt'), jointResult.stdout, 'utf8');

    const rawLinks = parseCliLinks(linkResult.stdout);
    const links = applyModelPoseToCliLinks(rawLinks, modelPose);
    const joints = parseCliJoints(jointResult.stdout, links);
    return { modelName, links, joints };
  } finally {
    await terminateProcess(server);
    const logOutput = Buffer.concat([...stdoutChunks, ...stderrChunks]).toString('utf8');
    await fs.writeFile(serverLogPath, logOutput, 'utf8');
  }
}

async function auditSample(sampleZipPath: string): Promise<SampleReport> {
  const sampleName = path.basename(sampleZipPath);
  const sampleKey = sanitizeName(sampleName.replace(/\.zip$/i, ''));
  const sampleOutputDir = path.join(OUTPUT_DIR, sampleKey);
  await fs.mkdir(sampleOutputDir, { recursive: true });

  const zipBytes = await fs.readFile(sampleZipPath);
  const zipFile = new File([zipBytes], path.basename(sampleZipPath), { type: 'application/zip' });
  const payload = await prepareImportPayload({
    files: [zipFile],
    existingPaths: [],
  });

  const preferredFileName = payload.preferredFileName;
  const allFileContents = buildAllFileContents(payload);
  const preferredFile = preferredFileName
    ? payload.robotFiles.find((file) => file.name === preferredFileName) ?? null
    : null;

  const importResult = preferredFile
    ? resolveRobotFileData(preferredFile, {
      availableFiles: payload.robotFiles,
      allFileContents,
    })
    : null;

  const report: SampleReport = {
    sample: sampleName,
    preferredFileName,
    importStatus: importResult?.status || 'missing_preferred_file',
    cliStatus: 'not_started',
    missingLinks: [],
    missingJoints: [],
    linkPoseMismatches: [],
    jointOriginMismatches: [],
    jointEndpointMismatches: [],
    collisionCountMismatches: [],
    collisionPoseMismatches: [],
    collisionTypeMismatches: [],
    notes: [],
  };

  if (!preferredFile || !preferredFileName) {
    report.notes.push('No preferred import file was selected from the ZIP payload.');
    return report;
  }
  if (!preferredFile.content) {
    report.notes.push('Preferred file has no text content.');
    return report;
  }
  if (!importResult || importResult.status !== 'ready') {
    report.notes.push('Import result was not ready.');
    return report;
  }

  const extractDir = path.join(sampleOutputDir, 'extracted');
  await unzipSample(sampleZipPath, extractDir);

  try {
    const extractedPreferredFilePath = await findExtractedPreferredFile(extractDir, preferredFileName);
    const cliFiles = await buildCliTruthFiles(extractedPreferredFilePath, preferredFileName, sampleOutputDir);
    const staticTruth = parseStaticTruthModel(preferredFileName, cliFiles.printedSdf);
    const cliTruth = await captureCliTruth(
      cliFiles.worldPath,
      cliFiles.modelName,
      cliFiles.modelPose,
      sampleOutputDir,
    );

    report.cliStatus = 'ready';
    report.cliTruthCounts = {
      links: Object.keys(cliTruth.links).length,
      joints: Object.values(cliTruth.joints).filter((joint) => joint.parent !== WORLD_FRAME).length,
      collisions: Object.values(staticTruth.links).reduce((sum, link) => sum + link.collisions.length, 0),
    };

    const robotData = importResult.robotData;
    const importedLinks = Object.keys(robotData.links).filter((name) => (
      !name.endsWith('__root') && !isSyntheticJointStageLinkName(name)
    ));
    const importedJoints = Object.values(robotData.joints)
      .filter((joint) => !joint.id.endsWith('__root_fixed') && !isSyntheticJointStageJoint(joint))
      .map((joint) => joint.id);
    const importedCollisionCount = importedLinks.reduce((sum, linkName) => (
      sum + getImportedCollisionBodies(robotData.links[linkName]).length
    ), 0);

    report.importedCounts = {
      links: importedLinks.length,
      joints: importedJoints.length,
      collisions: importedCollisionCount,
      syntheticLinks: Object.keys(robotData.links).length - importedLinks.length,
      syntheticJoints: Object.keys(robotData.joints).length - importedJoints.length,
    };

    const importedWorldPoses = computeImportedWorldPoses(robotData);

    Object.values(cliTruth.links).forEach((truthLink) => {
      const importedLink = robotData.links[truthLink.name];
      if (!importedLink) {
        report.missingLinks.push(truthLink.name);
        return;
      }

      const importedWorldPose = importedWorldPoses[truthLink.name];
      const delta = poseDifference(truthLink.worldPose, importedWorldPose);
      if (delta.translationError > POSITION_TOLERANCE || delta.rotationError > ROTATION_TOLERANCE) {
        report.linkPoseMismatches.push({
          name: truthLink.name,
          translationError: delta.translationError,
          rotationError: delta.rotationError,
          expected: truthLink.worldPose,
          actual: importedWorldPose,
        });
      }
    });

    Object.values(cliTruth.joints)
      .filter((truthJoint) => truthJoint.parent !== WORLD_FRAME)
      .forEach((truthJoint) => {
        const importedJoint = robotData.joints[truthJoint.name];
        if (!importedJoint) {
          report.missingJoints.push(truthJoint.name);
          return;
        }

        const normalizedImportedParent = resolveSyntheticStageTerminalLinkId(importedJoint.parentLinkId, robotData);
        const normalizedImportedChild = resolveSyntheticStageTerminalLinkId(importedJoint.childLinkId, robotData);

        if (normalizedImportedParent !== truthJoint.parent || normalizedImportedChild !== truthJoint.child) {
          report.jointEndpointMismatches.push({
            name: truthJoint.name,
            expectedParent: truthJoint.parent,
            expectedChild: truthJoint.child,
            actualParent: normalizedImportedParent,
            actualChild: normalizedImportedChild,
          });
        }

        const delta = poseDifference(truthJoint.parentRelativePose, importedJoint.origin);
        if (delta.translationError > POSITION_TOLERANCE || delta.rotationError > ROTATION_TOLERANCE) {
          report.jointOriginMismatches.push({
            name: truthJoint.name,
            translationError: delta.translationError,
            rotationError: delta.rotationError,
            expected: truthJoint.parentRelativePose,
            actual: importedJoint.origin,
          });
        }
      });

    Object.values(staticTruth.links).forEach((truthLink) => {
      const importedLink = robotData.links[truthLink.name];
      if (!importedLink) {
        return;
      }

      const importedWorldPose = importedWorldPoses[truthLink.name];
      const importedCollisions = getImportedCollisionBodies(importedLink);
      if (truthLink.collisions.length !== importedCollisions.length) {
        report.collisionCountMismatches.push({
          name: truthLink.name,
          expected: truthLink.collisions.length,
          actual: importedCollisions.length,
        });
      }

      truthLink.collisions.forEach((truthCollision, index) => {
        const importedCollision = importedCollisions[index];
        if (!importedCollision) {
          return;
        }

        const importedType = geometryTypeToLabel(importedCollision.type);
        if (truthCollision.type !== importedType) {
          report.collisionTypeMismatches.push({
            name: truthLink.name,
            index,
            expected: truthCollision.type,
            actual: importedType,
          });
        }

        const importedCollisionWorld = matrixToPose(
          poseToMatrix(importedWorldPose).multiply(poseToMatrix(importedCollision.origin || IDENTITY_POSE)),
        );
        const truthCollisionWorld = matrixToPose(
          poseToMatrix(cliTruth.links[truthLink.name]?.worldPose ?? importedWorldPose)
            .multiply(poseToMatrix(truthCollision.localPose)),
        );
        const delta = poseDifference(truthCollisionWorld, importedCollisionWorld);
        if (delta.translationError > POSITION_TOLERANCE || delta.rotationError > ROTATION_TOLERANCE) {
          report.collisionPoseMismatches.push({
            name: `${truthLink.name}#${index}`,
            translationError: delta.translationError,
            rotationError: delta.rotationError,
            expected: truthCollisionWorld,
            actual: importedCollisionWorld,
          });
        }
      });
    });

    const checkOutput = (await fs.readFile(path.join(sampleOutputDir, 'check.txt'), 'utf8')).trim();
    if (!checkOutput.includes('Valid.')) {
      report.notes.push(`ign sdf check output: ${checkOutput}`);
    }
  } catch (error) {
    report.cliStatus = 'error';
    report.notes.push(`CLI truth capture failed: ${error instanceof Error ? error.message : String(error)}`);
  }

  return report;
}

function issueCount(report: SampleReport): number {
  return report.missingLinks.length
    + report.missingJoints.length
    + report.linkPoseMismatches.length
    + report.jointOriginMismatches.length
    + report.jointEndpointMismatches.length
    + report.collisionCountMismatches.length
    + report.collisionPoseMismatches.length
    + report.collisionTypeMismatches.length
    + (report.cliStatus === 'ready' ? 0 : 1);
}

function summarizeReports(reports: SampleReport[]): string {
  const lines: string[] = [];
  lines.push('# SDF CLI Truth Audit');
  lines.push('');
  lines.push(`Audited samples: ${reports.length}`);
  lines.push('');

  reports.forEach((report) => {
    lines.push(`## ${report.sample}`);
    lines.push(`- preferred: ${report.preferredFileName ?? 'none'}`);
    lines.push(`- import status: ${report.importStatus}`);
    lines.push(`- cli status: ${report.cliStatus}`);
    if (report.cliTruthCounts && report.importedCounts) {
      lines.push(
        `- counts: cli links=${report.cliTruthCounts.links}, joints=${report.cliTruthCounts.joints}, collisions=${report.cliTruthCounts.collisions}; imported links=${report.importedCounts.links}, joints=${report.importedCounts.joints}, collisions=${report.importedCounts.collisions}`,
      );
    }
    lines.push(`- issue count: ${issueCount(report)}`);
    if (report.missingLinks.length) {
      lines.push(`- missing links: ${report.missingLinks.slice(0, 12).join(', ')}`);
    }
    if (report.missingJoints.length) {
      lines.push(`- missing joints: ${report.missingJoints.slice(0, 12).join(', ')}`);
    }
    if (report.linkPoseMismatches.length) {
      const first = report.linkPoseMismatches[0];
      lines.push(`- link pose mismatch example: ${first.name} (translation=${first.translationError.toExponential(3)}, rotation=${first.rotationError.toExponential(3)})`);
    }
    if (report.jointOriginMismatches.length) {
      const first = report.jointOriginMismatches[0];
      lines.push(`- joint mismatch example: ${first.name} (translation=${first.translationError.toExponential(3)}, rotation=${first.rotationError.toExponential(3)})`);
    }
    if (report.jointEndpointMismatches.length) {
      const first = report.jointEndpointMismatches[0];
      lines.push(`- joint endpoint mismatch example: ${first.name} expected ${first.expectedParent}->${first.expectedChild}, got ${first.actualParent}->${first.actualChild}`);
    }
    if (report.collisionCountMismatches.length) {
      const first = report.collisionCountMismatches[0];
      lines.push(`- collision count mismatch example: ${first.name} expected ${first.expected}, got ${first.actual}`);
    }
    if (report.collisionPoseMismatches.length) {
      const first = report.collisionPoseMismatches[0];
      lines.push(`- collision pose mismatch example: ${first.name} (translation=${first.translationError.toExponential(3)}, rotation=${first.rotationError.toExponential(3)})`);
    }
    if (report.collisionTypeMismatches.length) {
      const first = report.collisionTypeMismatches[0];
      lines.push(`- collision type mismatch example: ${first.name}#${first.index} expected ${first.expected}, got ${first.actual}`);
    }
    report.notes.forEach((note) => lines.push(`- note: ${note}`));
    lines.push('');
  });

  return `${lines.join('\n')}\n`;
}

async function main(): Promise<void> {
  const sdfDir = path.resolve('test/sdf');
  const entries = (await fs.readdir(sdfDir))
    .filter((name) => name.endsWith('.zip'))
    .sort((left, right) => left.localeCompare(right));

  await fs.mkdir(OUTPUT_DIR, { recursive: true });

  const reports: SampleReport[] = [];
  for (const entry of entries) {
    const fullPath = path.join(sdfDir, entry);
    reports.push(await auditSample(fullPath));
  }

  await fs.writeFile(path.join(OUTPUT_DIR, 'report.json'), JSON.stringify(reports, null, 2), 'utf8');
  await fs.writeFile(path.join(OUTPUT_DIR, 'report.md'), summarizeReports(reports), 'utf8');

  const highLevel = reports.map((report) => ({
    sample: report.sample,
    cliStatus: report.cliStatus,
    issues: issueCount(report),
    importStatus: report.importStatus,
  }));

  console.log(JSON.stringify(highLevel, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

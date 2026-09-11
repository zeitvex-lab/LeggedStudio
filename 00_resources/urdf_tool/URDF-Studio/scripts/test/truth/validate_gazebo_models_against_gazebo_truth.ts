import fs from 'node:fs/promises';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { pathToFileURL } from 'node:url';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { computeLinkWorldMatrices } from '@/core/robot';
import {
  GeometryType,
  JointType,
  type RobotData,
  type RobotFile,
  type UrdfJoint,
  type UrdfLink,
  type UrdfVisual,
  type Vector3,
} from '@/types';

const execFileAsync = promisify(execFile);

type EulerLike = { r: number; p: number; y: number };
type Pose = { xyz: Vector3; rpy: EulerLike };
type ParsedPose = { pose: Pose; relativeTo: string | null; specified: boolean };
type TruthBody = { type: string; localPose: Pose };

export type GazeboTruthLink = {
  name: string;
  worldPose: Pose;
  visuals: TruthBody[];
  collisions: TruthBody[];
};

export type GazeboTruthJoint = {
  name: string;
  type: JointType;
  parent: string;
  child: string;
  origin: Pose;
  axis?: Vector3;
  limit?: { lower: number; upper: number; effort: number; velocity: number };
  dynamics: { damping: number; friction: number };
};

export type GazeboTruthModel = {
  modelName: string;
  links: Record<string, GazeboTruthLink>;
  joints: Record<string, GazeboTruthJoint>;
};

type PoseMismatch = {
  name: string;
  translationError: number;
  rotationError: number;
  expected: Pose;
  actual: Pose;
};

type VectorMismatch = {
  name: string;
  error: number;
  expected?: Vector3;
  actual?: Vector3;
};

type ScalarMismatch = {
  name: string;
  field: string;
  expected: number;
  actual: number;
  error: number;
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

export type GazeboTruthComparison = {
  missingLinks: string[];
  unexpectedLinks: string[];
  missingJoints: string[];
  unexpectedJoints: string[];
  linkPoseMismatches: PoseMismatch[];
  jointOriginMismatches: PoseMismatch[];
  jointEndpointMismatches: EndpointMismatch[];
  jointTypeMismatches: Array<{ name: string; expected: JointType; actual: JointType }>;
  jointAxisMismatches: VectorMismatch[];
  jointLimitMismatches: ScalarMismatch[];
  jointDynamicsMismatches: ScalarMismatch[];
  visualCountMismatches: CountMismatch[];
  visualPoseMismatches: PoseMismatch[];
  visualTypeMismatches: TypeMismatch[];
  collisionCountMismatches: CountMismatch[];
  collisionPoseMismatches: PoseMismatch[];
  collisionTypeMismatches: TypeMismatch[];
};

type ModelAuditSummary = GazeboTruthComparison & {
  model: string;
  entryPath: string | null;
  importStatus: string;
  gazeboStatus: 'ready' | 'check_error' | 'print_error' | 'parse_error' | 'not_started';
  gazeboCheckOutput: string;
  gazeboPrintStderr: string;
  truthCounts?: {
    links: number;
    joints: number;
    visuals: number;
    collisions: number;
  };
  importedCounts?: {
    links: number;
    joints: number;
    visuals: number;
    collisions: number;
  };
  notes: string[];
};

type AuditReport = {
  generatedAt: string;
  datasetRoot: string;
  modelCount: number;
  readyCount: number;
  problemCount: number;
  issueCount: number;
  summaries: ModelAuditSummary[];
};

type CliOptions = {
  datasetRoot: string;
  outputPath: string;
  matches: string[];
  limit: number | null;
};

type DatasetContext = {
  availableFiles: RobotFile[];
  allFileContents: Record<string, string>;
  sourceFilesByModelDir: Map<string, string[]>;
};

const DEFAULT_DATASET_ROOT = path.resolve('test/gazebo_models');
const DEFAULT_OUTPUT_PATH = path.resolve('tmp/regression/gazebo-model-gazebo-truth.json');
const DEFAULT_MARKDOWN_PATH = path.resolve('tmp/regression/gazebo-model-gazebo-truth.md');
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
const ZERO_VECTOR: Vector3 = { x: 0, y: 0, z: 0 };
const ZERO_EULER: EulerLike = { r: 0, p: 0, y: 0 };
const IDENTITY_POSE: Pose = { xyz: ZERO_VECTOR, rpy: ZERO_EULER };
const IDENTITY_SCALE = new THREE.Vector3(1, 1, 1);
const MODEL_FRAME = '__model__';
const WORLD_FRAME = 'world';
const POSITION_TOLERANCE = 1e-5;
const ROTATION_TOLERANCE = 1e-4;
const VECTOR_TOLERANCE = 1e-5;
const SCALAR_TOLERANCE = 1e-6;
const SYNTHETIC_JOINT_STAGE_MARKER = '__joint_stage_';

function installDomGlobals(): void {
  if (typeof DOMParser !== 'undefined' && typeof Node !== 'undefined') {
    return;
  }
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  globalThis.window = dom.window as typeof globalThis.window;
  globalThis.document = dom.window.document as typeof globalThis.document;
  globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
  globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
  globalThis.Node = dom.window.Node as typeof Node;
  globalThis.Element = dom.window.Element as typeof Element;
  globalThis.Document = dom.window.Document as typeof Document;
  globalThis.self = globalThis;
}

function normalizePath(filePath: string): string {
  return filePath.replace(/\\/g, '/').replace(/^\/+/, '');
}

function isElementNode(node: Node | null | undefined): node is Element {
  return !!node && node.nodeType === 1;
}

function getDirectChildElements(parent: Element, tagName?: string): Element[] {
  return Array.from(parent.childNodes)
    .filter(isElementNode)
    .filter((child) => !tagName || child.tagName === tagName);
}

function getFirstDirectChild(parent: Element | null | undefined, tagName: string): Element | null {
  if (!parent) return null;
  return getDirectChildElements(parent, tagName)[0] ?? null;
}

function parseNumberTuple(text: string | null | undefined): number[] {
  return (text ?? '')
    .trim()
    .split(/\s+/)
    .map((value) => Number.parseFloat(value))
    .filter((value) => Number.isFinite(value));
}

function parseFloatSafe(value: string | null | undefined, fallback = 0): number {
  if (value == null) return fallback;
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseVec3(text: string | null | undefined): Vector3 {
  const [x = 0, y = 0, z = 0] = parseNumberTuple(text);
  return { x, y, z };
}

function parsePoseText(text: string | null | undefined): Pose {
  const [x = 0, y = 0, z = 0, r = 0, p = 0, yaw = 0] = parseNumberTuple(text);
  return {
    xyz: { x, y, z },
    rpy: { r, p, y: yaw },
  };
}

function parsePoseElement(parent: Element): ParsedPose {
  const poseEl = getFirstDirectChild(parent, 'pose');
  if (!poseEl) {
    return { pose: IDENTITY_POSE, relativeTo: null, specified: false };
  }
  return {
    pose: parsePoseText(poseEl.textContent),
    relativeTo: poseEl.getAttribute('relative_to')?.trim() || null,
    specified: true,
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

function vectorDifference(expected?: Vector3, actual?: Vector3): number {
  if (!expected || !actual) {
    return expected === actual ? 0 : Number.POSITIVE_INFINITY;
  }
  const dx = actual.x - expected.x;
  const dy = actual.y - expected.y;
  const dz = actual.z - expected.z;
  return Math.sqrt(dx * dx + dy * dy + dz * dz);
}

function compareScalar(expected: number, actual: number): number {
  if (!Number.isFinite(expected) || !Number.isFinite(actual)) {
    return Object.is(expected, actual) ? 0 : Number.POSITIVE_INFINITY;
  }
  return Math.abs(actual - expected);
}

function mapSdfJointType(rawType: string | null): JointType {
  switch ((rawType || '').trim().toLowerCase()) {
    case 'revolute':
      return JointType.REVOLUTE;
    case 'continuous':
      return JointType.CONTINUOUS;
    case 'prismatic':
      return JointType.PRISMATIC;
    case 'ball':
      return JointType.BALL;
    case 'planar':
      return JointType.PLANAR;
    case 'fixed':
    default:
      return JointType.FIXED;
  }
}

function parseTruthGeometryType(geometryEl: Element | null): string {
  if (!geometryEl) return 'none';
  if (getFirstDirectChild(geometryEl, 'box')) return 'box';
  if (getFirstDirectChild(geometryEl, 'cylinder')) return 'cylinder';
  if (getFirstDirectChild(geometryEl, 'sphere')) return 'sphere';
  if (getFirstDirectChild(geometryEl, 'capsule')) return 'capsule';
  if (getFirstDirectChild(geometryEl, 'plane')) return 'plane';
  if (getFirstDirectChild(geometryEl, 'mesh')) return 'mesh';
  if (getFirstDirectChild(geometryEl, 'heightmap')) return 'hfield';
  if (getFirstDirectChild(geometryEl, 'polyline')) return 'polyline';
  return 'none';
}

function geometryTypeToLabel(type: GeometryType | undefined): string {
  if (!type) return 'none';
  return String(type).toLowerCase();
}

function qualifyScopedName(name: string | null | undefined, namespacePrefix?: string): string {
  const normalizedName = String(name || '').trim();
  if (!normalizedName) return '';
  return namespacePrefix ? `${namespacePrefix}::${normalizedName}` : normalizedName;
}

function qualifyScopedReference(name: string | null | undefined, namespacePrefix?: string): string {
  const normalizedName = String(name || '').trim();
  if (!normalizedName) return '';
  if (
    normalizedName === MODEL_FRAME ||
    normalizedName === WORLD_FRAME ||
    normalizedName.includes('::')
  ) {
    return normalizedName;
  }
  return qualifyScopedName(normalizedName, namespacePrefix);
}

function resolvePoseWorldMatrix(
  pose: ParsedPose,
  defaultFrame: string,
  resolveFrameWorldMatrix: (frame: string) => THREE.Matrix4,
): THREE.Matrix4 {
  const baseFrame = pose.relativeTo || defaultFrame;
  const baseMatrix = resolveFrameWorldMatrix(baseFrame);
  return pose.specified ? baseMatrix.clone().multiply(poseToMatrix(pose.pose)) : baseMatrix.clone();
}

function parseTruthModel(
  modelEl: Element,
  truth: GazeboTruthModel,
  options: { parentMatrix?: THREE.Matrix4; namespacePrefix?: string } = {},
): void {
  const { parentMatrix = new THREE.Matrix4().identity(), namespacePrefix } = options;
  const modelPose = parsePoseElement(modelEl);
  const modelMatrix = parentMatrix.clone().multiply(poseToMatrix(modelPose.pose));
  const linkElements = new Map<string, Element>();
  const jointElements = new Map<string, Element>();
  const frameElements = new Map<string, Element>();

  for (const linkEl of getDirectChildElements(modelEl, 'link')) {
    const linkId = qualifyScopedName(linkEl.getAttribute('name')?.trim(), namespacePrefix);
    if (linkId) linkElements.set(linkId, linkEl);
  }
  for (const jointEl of getDirectChildElements(modelEl, 'joint')) {
    const jointId = qualifyScopedName(jointEl.getAttribute('name')?.trim(), namespacePrefix);
    if (jointId) jointElements.set(jointId, jointEl);
  }
  for (const frameEl of getDirectChildElements(modelEl, 'frame')) {
    const frameId = qualifyScopedName(frameEl.getAttribute('name')?.trim(), namespacePrefix);
    if (frameId) frameElements.set(frameId, frameEl);
  }

  const resolvedFrameCache = new Map<string, THREE.Matrix4>();
  const resolvingFrames = new Set<string>();
  resolvedFrameCache.set(MODEL_FRAME, modelMatrix);
  resolvedFrameCache.set(WORLD_FRAME, new THREE.Matrix4().identity());

  const resolveFrameWorldMatrix = (frame: string): THREE.Matrix4 => {
    const normalizedFrame = frame || MODEL_FRAME;
    const cached = resolvedFrameCache.get(normalizedFrame);
    if (cached) return cached;
    const knownTruthLink = truth.links[normalizedFrame];
    if (knownTruthLink) {
      return poseToMatrix(knownTruthLink.worldPose);
    }

    if (resolvingFrames.has(normalizedFrame)) {
      throw new Error(`SDF frame resolution cycle detected at ${normalizedFrame}`);
    }
    resolvingFrames.add(normalizedFrame);

    let resolved: THREE.Matrix4 | null = null;
    const linkEl = linkElements.get(normalizedFrame);
    if (linkEl) {
      resolved = resolvePoseWorldMatrix(parsePoseElement(linkEl), MODEL_FRAME, resolveFrameWorldMatrix);
    }

    if (!resolved) {
      const jointEl = jointElements.get(normalizedFrame);
      if (jointEl) {
        const childLinkId =
          qualifyScopedReference(
            getFirstDirectChild(jointEl, 'child')?.textContent?.trim(),
            namespacePrefix,
          ) || MODEL_FRAME;
        resolved = resolvePoseWorldMatrix(parsePoseElement(jointEl), childLinkId, resolveFrameWorldMatrix);
      }
    }

    if (!resolved) {
      const frameEl = frameElements.get(normalizedFrame);
      if (frameEl) {
        const attachedTo =
          qualifyScopedReference(frameEl.getAttribute('attached_to')?.trim(), namespacePrefix) ||
          MODEL_FRAME;
        resolved = resolvePoseWorldMatrix(parsePoseElement(frameEl), attachedTo, resolveFrameWorldMatrix);
      }
    }

    resolvingFrames.delete(normalizedFrame);
    if (!resolved) {
      throw new Error(`Unknown SDF frame reference: ${normalizedFrame}`);
    }
    resolvedFrameCache.set(normalizedFrame, resolved);
    return resolved;
  };

  for (const linkEl of getDirectChildElements(modelEl, 'link')) {
    const linkId = qualifyScopedName(linkEl.getAttribute('name')?.trim(), namespacePrefix);
    if (!linkId) continue;

    truth.links[linkId] = {
      name: linkId,
      worldPose: matrixToPose(resolveFrameWorldMatrix(linkId)),
      visuals: getDirectChildElements(linkEl, 'visual').map((visualEl) => ({
        type: parseTruthGeometryType(getFirstDirectChild(visualEl, 'geometry')),
        localPose: matrixToPose(
          resolveFrameWorldMatrix(linkId)
            .clone()
            .invert()
            .multiply(resolvePoseWorldMatrix(parsePoseElement(visualEl), linkId, resolveFrameWorldMatrix)),
        ),
      })),
      collisions: getDirectChildElements(linkEl, 'collision').map((collisionEl) => ({
        type: parseTruthGeometryType(getFirstDirectChild(collisionEl, 'geometry')),
        localPose: matrixToPose(
          resolveFrameWorldMatrix(linkId)
            .clone()
            .invert()
            .multiply(resolvePoseWorldMatrix(parsePoseElement(collisionEl), linkId, resolveFrameWorldMatrix)),
        ),
      })),
    };
  }

  for (const nestedModelEl of getDirectChildElements(modelEl, 'model')) {
    const nestedModelName = nestedModelEl.getAttribute('name')?.trim() || 'nested_model';
    parseTruthModel(nestedModelEl, truth, {
      parentMatrix: modelMatrix,
      namespacePrefix: qualifyScopedName(nestedModelName, namespacePrefix),
    });
  }

  for (const jointEl of getDirectChildElements(modelEl, 'joint')) {
    const jointId = qualifyScopedName(jointEl.getAttribute('name')?.trim(), namespacePrefix);
    if (!jointId) continue;

    const parent = qualifyScopedReference(
      getFirstDirectChild(jointEl, 'parent')?.textContent?.trim(),
      namespacePrefix,
    );
    const child = qualifyScopedReference(
      getFirstDirectChild(jointEl, 'child')?.textContent?.trim(),
      namespacePrefix,
    );
    if (!child) continue;

    const jointWorldMatrix = resolveFrameWorldMatrix(jointId);
    const parentWorldMatrix = parent && parent !== WORLD_FRAME
      ? resolveFrameWorldMatrix(parent)
      : new THREE.Matrix4().identity();
    const axisEl = getFirstDirectChild(jointEl, 'axis');
    const axisXyzEl = getFirstDirectChild(axisEl ?? jointEl, 'xyz');
    const limitEl = getFirstDirectChild(axisEl ?? jointEl, 'limit');
    const dynamicsEl = getFirstDirectChild(axisEl ?? jointEl, 'dynamics');
    const jointType = mapSdfJointType(jointEl.getAttribute('type'));
    let axis: Vector3 | undefined;

    if (
      jointType === JointType.REVOLUTE ||
      jointType === JointType.CONTINUOUS ||
      jointType === JointType.PRISMATIC ||
      jointType === JointType.PLANAR
    ) {
      const rawAxis = parseVec3(axisXyzEl?.textContent || '0 0 1');
      const expressedIn = axisXyzEl?.getAttribute('expressed_in')?.trim();
      const useParentModelFrameText = getFirstDirectChild(axisEl, 'use_parent_model_frame')
        ?.textContent?.trim()
        .toLowerCase();
      const frameName = expressedIn
        ? qualifyScopedReference(expressedIn, namespacePrefix)
        : useParentModelFrameText === 'true' || useParentModelFrameText === '1'
          ? MODEL_FRAME
          : null;
      if (frameName) {
        const axisFrameRotation = new THREE.Quaternion();
        const jointRotation = new THREE.Quaternion();
        resolveFrameWorldMatrix(frameName).decompose(new THREE.Vector3(), axisFrameRotation, new THREE.Vector3());
        jointWorldMatrix.decompose(new THREE.Vector3(), jointRotation, new THREE.Vector3());
        const axisVector = new THREE.Vector3(rawAxis.x, rawAxis.y, rawAxis.z)
          .applyQuaternion(axisFrameRotation)
          .applyQuaternion(jointRotation.invert());
        axis = { x: axisVector.x, y: axisVector.y, z: axisVector.z };
      } else {
        axis = rawAxis;
      }
    }

    truth.joints[jointId] = {
      name: jointId,
      type: jointType,
      parent,
      child,
      origin: matrixToPose(parentWorldMatrix.clone().invert().multiply(jointWorldMatrix)),
      axis,
      limit:
        jointType === JointType.REVOLUTE ||
        jointType === JointType.CONTINUOUS ||
        jointType === JointType.PRISMATIC
          ? {
              lower: parseFloatSafe(getFirstDirectChild(limitEl, 'lower')?.textContent, -Infinity),
              upper: parseFloatSafe(getFirstDirectChild(limitEl, 'upper')?.textContent, Infinity),
              effort: parseFloatSafe(getFirstDirectChild(limitEl, 'effort')?.textContent, 0),
              velocity: parseFloatSafe(getFirstDirectChild(limitEl, 'velocity')?.textContent, 0),
            }
          : undefined,
      dynamics: {
        damping: parseFloatSafe(getFirstDirectChild(dynamicsEl, 'damping')?.textContent, 0),
        friction: parseFloatSafe(getFirstDirectChild(dynamicsEl, 'friction')?.textContent, 0),
      },
    };
  }
}

function parseGazeboPrintedSdfTruth(xmlString: string, sourcePath: string): GazeboTruthModel {
  installDomGlobals();
  const doc = new DOMParser().parseFromString(xmlString.trim(), 'text/xml');
  if (doc.querySelector('parsererror')) {
    throw new Error(`Gazebo printed SDF is not XML parseable for ${sourcePath}`);
  }
  const modelEl = doc.querySelector('sdf > model, model');
  if (!modelEl) {
    throw new Error(`Gazebo printed SDF did not contain a <model> for ${sourcePath}`);
  }
  const modelName = modelEl.getAttribute('name')?.trim() || path.basename(sourcePath, '.sdf');
  const truth: GazeboTruthModel = { modelName, links: {}, joints: {} };
  parseTruthModel(modelEl, truth);
  return truth;
}

function getImportedBodies(link: UrdfLink, primary: 'visual' | 'collision'): UrdfVisual[] {
  const first = primary === 'visual' ? link.visual : link.collision;
  const rest = primary === 'visual' ? link.visualBodies : link.collisionBodies;
  const bodies: UrdfVisual[] = [];
  if (first.type !== GeometryType.NONE) bodies.push(first);
  return bodies.concat(rest || []);
}

function isSyntheticJointStageLinkName(linkName: string): boolean {
  return linkName.includes(SYNTHETIC_JOINT_STAGE_MARKER);
}

function isSyntheticJointStageJoint(joint: UrdfJoint): boolean {
  return joint.id.endsWith('_fixed') && isSyntheticJointStageLinkName(joint.parentLinkId);
}

function computeImportedWorldPoses(robotData: RobotData): Record<string, Pose> {
  const worldMatrices = computeLinkWorldMatrices(robotData);
  return Object.fromEntries(
    Object.keys(robotData.links).map((linkId) => [
      linkId,
      matrixToPose(worldMatrices[linkId] ?? new THREE.Matrix4().identity()),
    ]),
  );
}

function pushPoseMismatch(
  mismatches: PoseMismatch[],
  name: string,
  expected: Pose,
  actual: Pose,
): void {
  const delta = poseDifference(expected, actual);
  if (delta.translationError > POSITION_TOLERANCE || delta.rotationError > ROTATION_TOLERANCE) {
    mismatches.push({
      name,
      translationError: delta.translationError,
      rotationError: delta.rotationError,
      expected,
      actual,
    });
  }
}

function composeBodyWorldPose(linkWorldPose: Pose, bodyLocalPose: Pose): Pose {
  return matrixToPose(poseToMatrix(linkWorldPose).multiply(poseToMatrix(bodyLocalPose)));
}

function pushScalarMismatch(
  mismatches: ScalarMismatch[],
  name: string,
  field: string,
  expected: number,
  actual: number,
): void {
  const error = compareScalar(expected, actual);
  if (error > SCALAR_TOLERANCE) {
    mismatches.push({ name, field, expected, actual, error });
  }
}

export function compareGazeboTruthToRobotData(
  truth: GazeboTruthModel,
  robotData: RobotData,
): GazeboTruthComparison {
  const importedWorldPoses = computeImportedWorldPoses(robotData);
  const importedLinkIds = Object.keys(robotData.links).filter((name) => (
    !name.endsWith('__root') && !isSyntheticJointStageLinkName(name)
  ));
  const importedJoints = Object.values(robotData.joints).filter((joint) => (
    !joint.id.endsWith('__root_fixed') && !isSyntheticJointStageJoint(joint)
  ));
  const result: GazeboTruthComparison = {
    missingLinks: [],
    unexpectedLinks: importedLinkIds.filter((linkId) => !truth.links[linkId]).sort(),
    missingJoints: [],
    unexpectedJoints: importedJoints.map((joint) => joint.id).filter((jointId) => !truth.joints[jointId]).sort(),
    linkPoseMismatches: [],
    jointOriginMismatches: [],
    jointEndpointMismatches: [],
    jointTypeMismatches: [],
    jointAxisMismatches: [],
    jointLimitMismatches: [],
    jointDynamicsMismatches: [],
    visualCountMismatches: [],
    visualPoseMismatches: [],
    visualTypeMismatches: [],
    collisionCountMismatches: [],
    collisionPoseMismatches: [],
    collisionTypeMismatches: [],
  };

  for (const truthLink of Object.values(truth.links)) {
    const importedLink = robotData.links[truthLink.name];
    if (!importedLink) {
      result.missingLinks.push(truthLink.name);
      continue;
    }
    const importedLinkWorldPose = importedWorldPoses[truthLink.name] ?? IDENTITY_POSE;
    pushPoseMismatch(
      result.linkPoseMismatches,
      truthLink.name,
      truthLink.worldPose,
      importedLinkWorldPose,
    );

    const importedVisuals = getImportedBodies(importedLink, 'visual');
    if (importedVisuals.length !== truthLink.visuals.length) {
      result.visualCountMismatches.push({
        name: truthLink.name,
        expected: truthLink.visuals.length,
        actual: importedVisuals.length,
      });
    }
    truthLink.visuals.forEach((truthVisual, index) => {
      const importedVisual = importedVisuals[index];
      if (!importedVisual) return;
      const actual = geometryTypeToLabel(importedVisual.type);
      if (actual !== truthVisual.type) {
        result.visualTypeMismatches.push({
          name: truthLink.name,
          index,
          expected: truthVisual.type,
          actual,
        });
      }
      pushPoseMismatch(
        result.visualPoseMismatches,
        `${truthLink.name}#${index}`,
        composeBodyWorldPose(truthLink.worldPose, truthVisual.localPose),
        composeBodyWorldPose(importedLinkWorldPose, importedVisual.origin || IDENTITY_POSE),
      );
    });

    const importedCollisions = getImportedBodies(importedLink, 'collision');
    if (importedCollisions.length !== truthLink.collisions.length) {
      result.collisionCountMismatches.push({
        name: truthLink.name,
        expected: truthLink.collisions.length,
        actual: importedCollisions.length,
      });
    }
    truthLink.collisions.forEach((truthCollision, index) => {
      const importedCollision = importedCollisions[index];
      if (!importedCollision) return;
      const actual = geometryTypeToLabel(importedCollision.type);
      if (actual !== truthCollision.type) {
        result.collisionTypeMismatches.push({
          name: truthLink.name,
          index,
          expected: truthCollision.type,
          actual,
        });
      }
      pushPoseMismatch(
        result.collisionPoseMismatches,
        `${truthLink.name}#${index}`,
        composeBodyWorldPose(truthLink.worldPose, truthCollision.localPose),
        composeBodyWorldPose(importedLinkWorldPose, importedCollision.origin || IDENTITY_POSE),
      );
    });
  }
  result.missingLinks.sort();

  for (const truthJoint of Object.values(truth.joints)) {
    const importedJoint = robotData.joints[truthJoint.name];
    if (!importedJoint) {
      result.missingJoints.push(truthJoint.name);
      continue;
    }
    if (importedJoint.type !== truthJoint.type) {
      result.jointTypeMismatches.push({
        name: truthJoint.name,
        expected: truthJoint.type,
        actual: importedJoint.type,
      });
    }
    if (importedJoint.parentLinkId !== truthJoint.parent || importedJoint.childLinkId !== truthJoint.child) {
      result.jointEndpointMismatches.push({
        name: truthJoint.name,
        expectedParent: truthJoint.parent,
        expectedChild: truthJoint.child,
        actualParent: importedJoint.parentLinkId,
        actualChild: importedJoint.childLinkId,
      });
    }
    pushPoseMismatch(result.jointOriginMismatches, truthJoint.name, truthJoint.origin, importedJoint.origin);

    const axisError = vectorDifference(truthJoint.axis, importedJoint.axis);
    if (axisError > VECTOR_TOLERANCE) {
      result.jointAxisMismatches.push({
        name: truthJoint.name,
        error: axisError,
        expected: truthJoint.axis,
        actual: importedJoint.axis,
      });
    }

    if (truthJoint.limit || importedJoint.limit) {
      pushScalarMismatch(
        result.jointLimitMismatches,
        truthJoint.name,
        'lower',
        truthJoint.limit?.lower ?? Number.NaN,
        importedJoint.limit?.lower ?? Number.NaN,
      );
      pushScalarMismatch(
        result.jointLimitMismatches,
        truthJoint.name,
        'upper',
        truthJoint.limit?.upper ?? Number.NaN,
        importedJoint.limit?.upper ?? Number.NaN,
      );
      pushScalarMismatch(
        result.jointLimitMismatches,
        truthJoint.name,
        'effort',
        truthJoint.limit?.effort ?? Number.NaN,
        importedJoint.limit?.effort ?? Number.NaN,
      );
      pushScalarMismatch(
        result.jointLimitMismatches,
        truthJoint.name,
        'velocity',
        truthJoint.limit?.velocity ?? Number.NaN,
        importedJoint.limit?.velocity ?? Number.NaN,
      );
    }

    pushScalarMismatch(
      result.jointDynamicsMismatches,
      truthJoint.name,
      'damping',
      truthJoint.dynamics.damping,
      importedJoint.dynamics.damping,
    );
    pushScalarMismatch(
      result.jointDynamicsMismatches,
      truthJoint.name,
      'friction',
      truthJoint.dynamics.friction,
      importedJoint.dynamics.friction,
    );
  }
  result.missingJoints.sort();

  return result;
}

function issueCount(report: GazeboTruthComparison & { gazeboStatus?: string; importStatus?: string }): number {
  return report.missingLinks.length
    + report.unexpectedLinks.length
    + report.missingJoints.length
    + report.unexpectedJoints.length
    + report.linkPoseMismatches.length
    + report.jointOriginMismatches.length
    + report.jointEndpointMismatches.length
    + report.jointTypeMismatches.length
    + report.jointAxisMismatches.length
    + report.jointLimitMismatches.length
    + report.jointDynamicsMismatches.length
    + report.visualCountMismatches.length
    + report.visualPoseMismatches.length
    + report.visualTypeMismatches.length
    + report.collisionCountMismatches.length
    + report.collisionPoseMismatches.length
    + report.collisionTypeMismatches.length
    + (report.gazeboStatus && report.gazeboStatus !== 'ready' ? 1 : 0)
    + (report.importStatus && report.importStatus !== 'ready' ? 1 : 0);
}

function emptyComparison(): GazeboTruthComparison {
  return {
    missingLinks: [],
    unexpectedLinks: [],
    missingJoints: [],
    unexpectedJoints: [],
    linkPoseMismatches: [],
    jointOriginMismatches: [],
    jointEndpointMismatches: [],
    jointTypeMismatches: [],
    jointAxisMismatches: [],
    jointLimitMismatches: [],
    jointDynamicsMismatches: [],
    visualCountMismatches: [],
    visualPoseMismatches: [],
    visualTypeMismatches: [],
    collisionCountMismatches: [],
    collisionPoseMismatches: [],
    collisionTypeMismatches: [],
  };
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
      if (!value) throw new Error(`Missing value for ${arg}`);
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
  async function visit(currentDir: string): Promise<void> {
    const entries = await fs.readdir(currentDir, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name));
    for (const entry of entries) {
      if (entry.name.startsWith('.')) continue;
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

function detectSourceFormat(filePath: string): Extract<RobotFile['format'], 'mjcf' | 'sdf' | 'urdf' | 'xacro'> {
  const extension = path.extname(filePath).toLowerCase();
  if (extension === '.sdf') return 'sdf';
  if (extension === '.xacro') return 'xacro';
  if (extension === '.mjcf') return 'mjcf';
  return 'urdf';
}

async function createDatasetContext(datasetRoot: string): Promise<DatasetContext> {
  const files = await collectFiles(datasetRoot);
  const availableFiles: RobotFile[] = [];
  const allFileContents: Record<string, string> = {};
  const sourceFilesByModelDir = new Map<string, string[]>();

  for (const absolutePath of files) {
    const relativePath = normalizePath(path.relative(datasetRoot, absolutePath));
    const [modelDirName] = relativePath.split('/');
    const extension = path.extname(absolutePath).toLowerCase();
    if (TEXT_EXTENSIONS.has(extension)) {
      allFileContents[relativePath] = await fs.readFile(absolutePath, 'utf8');
    }
    if (SOURCE_EXTENSIONS.has(extension)) {
      const sourceFiles = sourceFilesByModelDir.get(modelDirName) ?? [];
      sourceFiles.push(relativePath);
      sourceFilesByModelDir.set(modelDirName, sourceFiles);
      availableFiles.push({
        name: relativePath,
        format: detectSourceFormat(absolutePath),
        content: allFileContents[relativePath] ?? (await fs.readFile(absolutePath, 'utf8')),
      });
    }
  }

  return { availableFiles, allFileContents, sourceFilesByModelDir };
}

function choosePreferredEntry(modelDirName: string, sourceFiles: string[]): string | null {
  const preferredCandidates = [
    `${modelDirName}/model.sdf`,
    `${modelDirName}/${modelDirName}.sdf`,
    `${modelDirName}/model.urdf`,
    `${modelDirName}/${modelDirName}.urdf`,
  ];
  for (const candidate of preferredCandidates) {
    if (sourceFiles.includes(candidate)) return candidate;
  }
  return sourceFiles.find((file) => file.endsWith('.sdf')) ?? sourceFiles[0] ?? null;
}

async function runGazeboSdfCommand(
  args: string[],
  datasetRoot: string,
): Promise<{ stdout: string; stderr: string }> {
  const env = {
    ...process.env,
    SDF_PATH: [datasetRoot, process.env.SDF_PATH].filter(Boolean).join(path.delimiter),
  };
  const { stdout, stderr } = await execFileAsync('ign', args, {
    env,
    timeout: 60_000,
    maxBuffer: 128 * 1024 * 1024,
  });
  return { stdout: String(stdout), stderr: String(stderr) };
}

function createBaseSummary(model: string, entryPath: string | null): ModelAuditSummary {
  return {
    model,
    entryPath,
    importStatus: 'not_started',
    gazeboStatus: 'not_started',
    gazeboCheckOutput: '',
    gazeboPrintStderr: '',
    notes: [],
    ...emptyComparison(),
  };
}

function importedCounts(robotData: RobotData): ModelAuditSummary['importedCounts'] {
  const links = Object.values(robotData.links).filter((link) => (
    !link.id.endsWith('__root') && !isSyntheticJointStageLinkName(link.id)
  ));
  const joints = Object.values(robotData.joints).filter((joint) => (
    !joint.id.endsWith('__root_fixed') && !isSyntheticJointStageJoint(joint)
  ));
  return {
    links: links.length,
    joints: joints.length,
    visuals: links.reduce((sum, link) => sum + getImportedBodies(link, 'visual').length, 0),
    collisions: links.reduce((sum, link) => sum + getImportedBodies(link, 'collision').length, 0),
  };
}

function truthCounts(truth: GazeboTruthModel): NonNullable<ModelAuditSummary['truthCounts']> {
  const links = Object.values(truth.links);
  return {
    links: links.length,
    joints: Object.keys(truth.joints).length,
    visuals: links.reduce((sum, link) => sum + link.visuals.length, 0),
    collisions: links.reduce((sum, link) => sum + link.collisions.length, 0),
  };
}

async function auditModel(
  datasetRoot: string,
  datasetContext: DatasetContext,
  modelDirName: string,
): Promise<ModelAuditSummary> {
  const entryPath = choosePreferredEntry(
    modelDirName,
    datasetContext.sourceFilesByModelDir.get(modelDirName) ?? [],
  );
  const summary = createBaseSummary(modelDirName, entryPath);
  if (!entryPath) {
    summary.importStatus = 'missing_entry';
    summary.gazeboStatus = 'print_error';
    summary.notes.push('No SDF/URDF/Xacro entry file found.');
    return summary;
  }

  const sourceFile = datasetContext.availableFiles.find((file) => file.name === entryPath) ?? null;
  if (!sourceFile) {
    summary.importStatus = 'missing_entry';
    summary.gazeboStatus = 'print_error';
    summary.notes.push(`Preferred entry missing from availableFiles: ${entryPath}`);
    return summary;
  }

  const importResult = resolveRobotFileData(sourceFile, {
    availableFiles: datasetContext.availableFiles,
    allFileContents: datasetContext.allFileContents,
  });
  summary.importStatus = importResult.status;
  if (importResult.status === 'ready') {
    summary.importedCounts = importedCounts(importResult.robotData);
  } else if (importResult.status === 'error') {
    summary.notes.push(`Import error: ${importResult.reason}: ${importResult.message ?? ''}`.trim());
  }

  const absoluteEntryPath = path.join(datasetRoot, entryPath);
  try {
    const check = await runGazeboSdfCommand(['sdf', '-k', absoluteEntryPath], datasetRoot);
    summary.gazeboCheckOutput = `${check.stdout}${check.stderr}`.trim();
  } catch (error) {
    summary.gazeboStatus = 'check_error';
    summary.notes.push(`Gazebo sdf -k failed: ${error instanceof Error ? error.message : String(error)}`);
    return summary;
  }

  let printed: { stdout: string; stderr: string };
  try {
    printed = await runGazeboSdfCommand(['sdf', '-p', absoluteEntryPath], datasetRoot);
    summary.gazeboPrintStderr = printed.stderr.trim();
  } catch (error) {
    summary.gazeboStatus = 'print_error';
    summary.notes.push(`Gazebo sdf -p failed: ${error instanceof Error ? error.message : String(error)}`);
    return summary;
  }

  let truth: GazeboTruthModel;
  try {
    truth = parseGazeboPrintedSdfTruth(printed.stdout, entryPath);
    summary.gazeboStatus = 'ready';
    summary.truthCounts = truthCounts(truth);
  } catch (error) {
    summary.gazeboStatus = 'parse_error';
    summary.notes.push(`Failed to parse Gazebo printed SDF: ${error instanceof Error ? error.message : String(error)}`);
    return summary;
  }

  if (summary.gazeboPrintStderr) {
    summary.notes.push(`Gazebo sdf -p stderr: ${summary.gazeboPrintStderr.split(/\r?\n/).slice(0, 3).join(' | ')}`);
  }
  if (importResult.status === 'ready') {
    Object.assign(summary, compareGazeboTruthToRobotData(truth, importResult.robotData));
  }
  return summary;
}

function formatIssueExample<T>(items: T[], render: (item: T) => string): string | null {
  const first = items[0];
  return first ? render(first) : null;
}

function summarizeReport(report: AuditReport): string {
  const lines: string[] = [];
  lines.push('# Gazebo Models vs Gazebo Truth Audit');
  lines.push('');
  lines.push(`Generated: ${report.generatedAt}`);
  lines.push(`Dataset: ${report.datasetRoot}`);
  lines.push(`Models audited: ${report.modelCount}`);
  lines.push(`Ready: ${report.readyCount}`);
  lines.push(`Problem models: ${report.problemCount}`);
  lines.push(`Issue count: ${report.issueCount}`);
  lines.push('');

  for (const summary of report.summaries) {
    const issues = issueCount(summary);
    lines.push(`## ${summary.model}`);
    lines.push(`- entry: ${summary.entryPath ?? 'none'}`);
    lines.push(`- import status: ${summary.importStatus}`);
    lines.push(`- gazebo status: ${summary.gazeboStatus}`);
    if (summary.truthCounts && summary.importedCounts) {
      lines.push(
        `- counts: truth links=${summary.truthCounts.links}, joints=${summary.truthCounts.joints}, visuals=${summary.truthCounts.visuals}, collisions=${summary.truthCounts.collisions}; imported links=${summary.importedCounts.links}, joints=${summary.importedCounts.joints}, visuals=${summary.importedCounts.visuals}, collisions=${summary.importedCounts.collisions}`,
      );
    }
    lines.push(`- issue count: ${issues}`);
    const examples = [
      formatIssueExample(summary.missingLinks, (item) => `missing link: ${item}`),
      formatIssueExample(summary.unexpectedLinks, (item) => `unexpected link: ${item}`),
      formatIssueExample(summary.missingJoints, (item) => `missing joint: ${item}`),
      formatIssueExample(summary.unexpectedJoints, (item) => `unexpected joint: ${item}`),
      formatIssueExample(
        summary.linkPoseMismatches,
        (item) => `link pose mismatch: ${item.name} translation=${item.translationError.toExponential(3)} rotation=${item.rotationError.toExponential(3)}`,
      ),
      formatIssueExample(
        summary.jointOriginMismatches,
        (item) => `joint origin mismatch: ${item.name} translation=${item.translationError.toExponential(3)} rotation=${item.rotationError.toExponential(3)}`,
      ),
      formatIssueExample(
        summary.jointAxisMismatches,
        (item) => `joint axis mismatch: ${item.name} error=${item.error.toExponential(3)}`,
      ),
      formatIssueExample(
        summary.jointLimitMismatches,
        (item) => `joint limit mismatch: ${item.name}.${item.field} expected=${item.expected} actual=${item.actual}`,
      ),
      formatIssueExample(
        summary.jointDynamicsMismatches,
        (item) => `joint dynamics mismatch: ${item.name}.${item.field} expected=${item.expected} actual=${item.actual}`,
      ),
      formatIssueExample(
        summary.visualCountMismatches,
        (item) => `visual count mismatch: ${item.name} expected=${item.expected} actual=${item.actual}`,
      ),
      formatIssueExample(
        summary.visualPoseMismatches,
        (item) => `visual pose mismatch: ${item.name} translation=${item.translationError.toExponential(3)} rotation=${item.rotationError.toExponential(3)}`,
      ),
      formatIssueExample(
        summary.collisionCountMismatches,
        (item) => `collision count mismatch: ${item.name} expected=${item.expected} actual=${item.actual}`,
      ),
      formatIssueExample(
        summary.collisionPoseMismatches,
        (item) => `collision pose mismatch: ${item.name} translation=${item.translationError.toExponential(3)} rotation=${item.rotationError.toExponential(3)}`,
      ),
    ].filter((line): line is string => Boolean(line));
    examples.slice(0, 8).forEach((example) => lines.push(`- ${example}`));
    summary.notes.slice(0, 4).forEach((note) => lines.push(`- note: ${note}`));
    lines.push('');
  }

  return `${lines.join('\n')}\n`;
}

async function main(): Promise<void> {
  installDomGlobals();
  const options = parseCliArgs(process.argv.slice(2));
  const datasetContext = await createDatasetContext(options.datasetRoot);
  const requestedModelDirs = (await fs.readdir(options.datasetRoot, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('.'))
    .map((entry) => entry.name)
    .sort((left, right) => left.localeCompare(right));
  const filteredModelDirs = requestedModelDirs.filter((modelDirName) => {
    if (options.matches.length === 0) return true;
    const haystack = modelDirName.toLowerCase();
    return options.matches.every((filter) => haystack.includes(filter));
  });
  const modelDirs = options.limit == null ? filteredModelDirs : filteredModelDirs.slice(0, options.limit);

  const summaries: ModelAuditSummary[] = [];
  for (const modelDirName of modelDirs) {
    summaries.push(await auditModel(options.datasetRoot, datasetContext, modelDirName));
  }

  const report: AuditReport = {
    generatedAt: new Date().toISOString(),
    datasetRoot: options.datasetRoot,
    modelCount: summaries.length,
    readyCount: summaries.filter((summary) => summary.importStatus === 'ready' && summary.gazeboStatus === 'ready').length,
    problemCount: summaries.filter((summary) => issueCount(summary) > 0).length,
    issueCount: summaries.reduce((sum, summary) => sum + issueCount(summary), 0),
    summaries,
  };
  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
  await fs.writeFile(options.outputPath, JSON.stringify(report, null, 2), 'utf8');

  const markdownPath = options.outputPath === DEFAULT_OUTPUT_PATH
    ? DEFAULT_MARKDOWN_PATH
    : options.outputPath.replace(/\.json$/i, '.md');
  await fs.writeFile(markdownPath, summarizeReport(report), 'utf8');

  console.log(JSON.stringify({
    outputPath: options.outputPath,
    markdownPath,
    modelCount: report.modelCount,
    readyCount: report.readyCount,
    problemCount: report.problemCount,
    issueCount: report.issueCount,
  }, null, 2));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exitCode = 1;
  });
}

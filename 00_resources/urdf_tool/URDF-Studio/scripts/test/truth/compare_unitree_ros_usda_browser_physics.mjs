#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

export const DEFAULT_BROWSER_REPORT_PATH = path.resolve(
  'tmp/regression/unitree-ros-usda-selected.json',
);
export const DEFAULT_TRUTH_PATH = path.resolve(
  'tmp/regression/unitree-ros-usda-isaaclab22-physics.json',
);
export const DEFAULT_OUTPUT_PATH = path.resolve(
  'tmp/regression/unitree-ros-usda-browser-physics-compare.json',
);
export const DEFAULT_MASS_TOLERANCE = 1e-6;
export const DEFAULT_COM_TOLERANCE = 1e-6;
export const DEFAULT_INERTIA_TOLERANCE = 1e-6;
export const DEFAULT_PRINCIPAL_AXES_TOLERANCE = 1e-6;
export const DEFAULT_JOINT_FRAME_TOLERANCE = 1e-6;
export const DEFAULT_LINK_POSITION_TOLERANCE = 1e-5;
export const DEFAULT_LINK_ORIENTATION_TOLERANCE = 2e-4;
export const DEFAULT_WORLD_POSITION_TOLERANCE = DEFAULT_LINK_POSITION_TOLERANCE;
export const DEFAULT_MATERIAL_COLOR_TOLERANCE = 0.002;

const UNITREE_USDA_PREFIX = 'test/unitree_ros_usda/';

function normalizePathToken(value) {
  return String(value ?? '').replace(/\\/g, '/').replace(/^\.\//, '');
}

function stripUnitreePrefix(value) {
  const normalized = normalizePathToken(value);
  const index = normalized.indexOf(UNITREE_USDA_PREFIX);
  return index >= 0 ? normalized.slice(index + UNITREE_USDA_PREFIX.length) : normalized;
}

function lastPathSegment(value) {
  const normalized = normalizePathToken(value).replace(/\/+$/, '');
  if (!normalized || normalized === '/') {
    return '';
  }
  return normalized.slice(normalized.lastIndexOf('/') + 1);
}

function finiteNumberOrZero(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : 0;
}

function vector3OrZero(value) {
  if (Array.isArray(value)) {
    return [
      finiteNumberOrZero(value[0]),
      finiteNumberOrZero(value[1]),
      finiteNumberOrZero(value[2]),
    ];
  }

  if (value && typeof value === 'object') {
    return [
      finiteNumberOrZero(value.x),
      finiteNumberOrZero(value.y),
      finiteNumberOrZero(value.z),
    ];
  }

  return [0, 0, 0];
}

function vector3OrNull(value) {
  if (Array.isArray(value) && value.length >= 3) {
    const result = [Number(value[0]), Number(value[1]), Number(value[2])];
    return result.every(Number.isFinite) ? result : null;
  }

  if (value && typeof value === 'object') {
    const result = [Number(value.x), Number(value.y), Number(value.z)];
    return result.every(Number.isFinite) ? result : null;
  }

  return null;
}

function quaternionWxyzOrIdentity(value) {
  let quaternion = null;

  if (Array.isArray(value)) {
    quaternion = [
      finiteNumberOrZero(value[0]),
      finiteNumberOrZero(value[1]),
      finiteNumberOrZero(value[2]),
      finiteNumberOrZero(value[3]),
    ];
  } else if (value && typeof value === 'object') {
    quaternion = [
      finiteNumberOrZero(value.w),
      finiteNumberOrZero(value.x),
      finiteNumberOrZero(value.y),
      finiteNumberOrZero(value.z),
    ];
  }

  if (!quaternion) {
    return [1, 0, 0, 0];
  }

  const norm = Math.hypot(quaternion[0], quaternion[1], quaternion[2], quaternion[3]);
  if (norm <= 1e-12) {
    return [1, 0, 0, 0];
  }

  return quaternion.map((entry) => entry / norm);
}

function vectorDistance(left, right) {
  return Math.hypot(left[0] - right[0], left[1] - right[1], left[2] - right[2]);
}

function subtractVector3(left, right) {
  return [left[0] - right[0], left[1] - right[1], left[2] - right[2]];
}

function median(values) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function quaternionDistanceWxyz(left, right) {
  const direct = Math.hypot(
    left[0] - right[0],
    left[1] - right[1],
    left[2] - right[2],
    left[3] - right[3],
  );
  const negated = Math.hypot(
    left[0] + right[0],
    left[1] + right[1],
    left[2] + right[2],
    left[3] + right[3],
  );
  return Math.min(direct, negated);
}

function quaternionWxyzFromXyzwOrIdentity(value) {
  if (!Array.isArray(value)) {
    return [1, 0, 0, 0];
  }
  return quaternionWxyzOrIdentity([value[3], value[0], value[1], value[2]]);
}

function eulerZyxToQuaternionWxyz(rpy) {
  const x = finiteNumberOrZero(rpy?.r);
  const y = finiteNumberOrZero(rpy?.p);
  const z = finiteNumberOrZero(rpy?.y);
  const c1 = Math.cos(x / 2);
  const c2 = Math.cos(y / 2);
  const c3 = Math.cos(z / 2);
  const s1 = Math.sin(x / 2);
  const s2 = Math.sin(y / 2);
  const s3 = Math.sin(z / 2);
  return [
    c1 * c2 * c3 + s1 * s2 * s3,
    s1 * c2 * c3 - c1 * s2 * s3,
    c1 * s2 * c3 + s1 * c2 * s3,
    c1 * c2 * s3 - s1 * s2 * c3,
  ];
}

function getBrowserLinkName(link) {
  return String(link?.name ?? link?.id ?? '');
}

function getBrowserLinkCenterOfMass(link) {
  return vector3OrZero(link?.centerOfMass?.xyz);
}

function getBrowserLinkDiagonalInertia(link) {
  return [
    finiteNumberOrZero(link?.inertia?.ixx),
    finiteNumberOrZero(link?.inertia?.iyy),
    finiteNumberOrZero(link?.inertia?.izz),
  ];
}

function getBrowserLinkPrincipalAxes(link) {
  return eulerZyxToQuaternionWxyz(link?.centerOfMass?.rpy);
}

function getBrowserLinkPoseName(linkPose) {
  return String(linkPose?.linkName ?? linkPose?.linkId ?? '');
}

function getBrowserLinkWorldPose(linkPose) {
  return {
    position: vector3OrZero(linkPose?.position),
    orientationWxyz: quaternionWxyzFromXyzwOrIdentity(linkPose?.quaternion),
  };
}

function getBrowserRuntimeLinkName(link) {
  return String(link?.name ?? link?.linkName ?? link?.id ?? '');
}

function getBrowserRuntimeLinkWorldPosition(runtimeLink) {
  return vector3OrNull(runtimeLink?.position);
}

function getBrowserJointName(joint) {
  return String(joint?.name ?? joint?.id ?? '');
}

function getNativeJointName(joint) {
  return String(joint?.jointName || lastPathSegment(joint?.jointPath) || '');
}

function getTruthJointName(joint) {
  return (
    String(joint?.name || '').trim() ||
    lastPathSegment(joint?.fullPath) ||
    lastPathSegment(joint?.path) ||
    lastPathSegment(joint?.jointPath)
  );
}

function isParentlessRootFixedJoint(joint) {
  const body0Path = String(joint?.body0Path || joint?.body0FullPath || '').trim();
  const body1Path = String(joint?.body1Path || joint?.body1FullPath || '').trim();
  const parentLinkPath = String(joint?.parentLinkPath || joint?.parentBodyPath || '').trim();
  const childLinkPath = String(joint?.childLinkPath || joint?.childBodyPath || '').trim();
  const type = String(joint?.type || joint?.jointType || joint?.jointTypeName || '').toLowerCase();
  const normalizedName = getTruthJointName(joint).toLowerCase().replace(/[^a-z0-9]/g, '');
  const hasParentSide = Boolean(body0Path || parentLinkPath);
  const hasChildSide = Boolean(body1Path || childLinkPath);
  const isRootNamedJoint = normalizedName === 'root' || normalizedName === 'rootjoint';

  if (hasParentSide && hasChildSide) {
    return false;
  }

  return (!hasParentSide && type.includes('fixed')) || isRootNamedJoint;
}

function isSyntheticBrowserVisualLink(link) {
  const linkName = getBrowserLinkName(link);
  const normalizedName = linkName.toLowerCase();
  const inertiallyEmpty =
    Math.abs(finiteNumberOrZero(link?.mass)) <= 1e-12 &&
    vectorDistance(getBrowserLinkCenterOfMass(link), [0, 0, 0]) <= 1e-12;

  if (!inertiallyEmpty) {
    return false;
  }

  return (
    normalizedName === 'world' ||
    /^visuals_proto_(?:mesh|box|sphere|capsule|cylinder)_id\d+$/.test(normalizedName) ||
    /__.*_visuals_(?:mesh|box|sphere|capsule|cylinder)_\d+$/.test(normalizedName)
  );
}

function getBrowserJointFrame(joint) {
  return {
    localPos0: vector3OrZero(joint?.usdPhysics?.localPos0),
    localRot0Wxyz: quaternionWxyzOrIdentity(joint?.usdPhysics?.localRot0Wxyz),
    localPos1: vector3OrZero(joint?.usdPhysics?.localPos1),
    localRot1Wxyz: quaternionWxyzOrIdentity(joint?.usdPhysics?.localRot1Wxyz),
  };
}

function getNativeJointFrame(joint) {
  return {
    localPos0: vector3OrZero(joint?.localPos0),
    localRot0Wxyz: quaternionWxyzOrIdentity(joint?.localRot0Wxyz),
    localPos1: vector3OrZero(joint?.localPos1),
    localRot1Wxyz: quaternionWxyzOrIdentity(joint?.localRot1Wxyz),
  };
}

function getTruthJointFrame(joint) {
  return {
    localPos0: vector3OrZero(joint?.localPos0),
    localRot0Wxyz: quaternionWxyzOrIdentity(joint?.localRot0 ?? joint?.localRot0Wxyz),
    localPos1: vector3OrZero(joint?.localPos1),
    localRot1Wxyz: quaternionWxyzOrIdentity(joint?.localRot1 ?? joint?.localRot1Wxyz),
  };
}

function compareJointFrame({
  addFailure,
  modelKey,
  modelStats,
  jointName,
  observedFrame,
  truthFrame,
  tolerance,
  sourceLabel,
  mismatchCounterKey,
  maxErrKey,
  worstKey,
}) {
  const prefix = sourceLabel === 'native' ? 'native-joint' : 'joint';
  const fields = [
    {
      name: 'localPos0',
      observed: observedFrame.localPos0,
      truth: truthFrame.localPos0,
      err: vectorDistance(observedFrame.localPos0, truthFrame.localPos0),
    },
    {
      name: 'localRot0Wxyz',
      observed: observedFrame.localRot0Wxyz,
      truth: truthFrame.localRot0Wxyz,
      err: quaternionDistanceWxyz(observedFrame.localRot0Wxyz, truthFrame.localRot0Wxyz),
    },
    {
      name: 'localPos1',
      observed: observedFrame.localPos1,
      truth: truthFrame.localPos1,
      err: vectorDistance(observedFrame.localPos1, truthFrame.localPos1),
    },
    {
      name: 'localRot1Wxyz',
      observed: observedFrame.localRot1Wxyz,
      truth: truthFrame.localRot1Wxyz,
      err: quaternionDistanceWxyz(observedFrame.localRot1Wxyz, truthFrame.localRot1Wxyz),
    },
  ];

  for (const field of fields) {
    if (field.err > modelStats[maxErrKey]) {
      modelStats[maxErrKey] = field.err;
      modelStats[worstKey] = {
        joint: jointName,
        field: field.name,
        observed: field.observed,
        truth: field.truth,
        err: field.err,
      };
    }
    if (field.err > tolerance) {
      modelStats[mismatchCounterKey] += 1;
      addFailure({
        type: `${prefix}-${field.name}-mismatch`,
        model: modelKey,
        joint: jointName,
        observed: field.observed,
        truth: field.truth,
        err: field.err,
        tolerance,
      });
    }
  }
}

function getTruthBodyName(body) {
  return (
    String(body?.name || '').trim() ||
    lastPathSegment(body?.fullPath) ||
    lastPathSegment(body?.path) ||
    lastPathSegment(body?.linkPath)
  );
}

function getTruthBodyWorldPose(body) {
  return {
    position: vector3OrZero(body?.worldPose?.position),
    orientationWxyz: quaternionWxyzOrIdentity(body?.worldPose?.orientationWxyz),
  };
}

function getTruthBodyWorldPosition(body) {
  return vector3OrNull(body?.worldPosition) ?? vector3OrNull(body?.worldPose?.position);
}

function getGeometryType(value) {
  return String(value?.type || '').trim().toLowerCase();
}

function isAuthoredCollisionGeometry(value) {
  const type = getGeometryType(value);
  return Boolean(type && type !== 'none');
}

function getBrowserLinkCollisionCount(link) {
  if (link?.collisionCount != null && Number.isFinite(Number(link.collisionCount))) {
    return Math.max(0, Number(link.collisionCount));
  }

  let count = isAuthoredCollisionGeometry(link?.collision) ? 1 : 0;
  if (Array.isArray(link?.collisionBodies)) {
    count += link.collisionBodies.filter((entry) => isAuthoredCollisionGeometry(entry?.geometry || entry)).length;
  }
  return count;
}

function buildBrowserCollisionCountByName(result, browserLinks) {
  const map = new Map();
  const hasStoreCollisionCounts = browserLinks.some(
    (link) => link?.collisionCount != null && Number.isFinite(Number(link.collisionCount)),
  );
  const collisionSummaryLinks = Array.isArray(result?.selectedUsdSceneSummary?.collisionSummary?.links)
    ? result.selectedUsdSceneSummary.collisionSummary.links
    : [];

  if (!hasStoreCollisionCounts && collisionSummaryLinks.length > 0) {
    for (const entry of collisionSummaryLinks) {
      const linkName = String(entry?.linkName || lastPathSegment(entry?.linkPath) || '').trim();
      if (!linkName) {
        continue;
      }
      map.set(linkName, (map.get(linkName) || 0) + Math.max(0, Number(entry?.descriptorCount) || 0));
    }
    return map;
  }

  for (const link of browserLinks) {
    const linkName = getBrowserLinkName(link);
    if (!linkName) {
      continue;
    }
    map.set(linkName, getBrowserLinkCollisionCount(link));
  }

  return map;
}

function getResultModelKey(result) {
  return String(result?.modelKey || result?.targetFileName || result?.selectedFileName || '');
}

function getTruthCandidatesForResult(result) {
  const rawCandidates = [
    result?.modelKey,
    result?.targetFileName,
    result?.selectedFileName,
    result?.snapshot?.selectedFile?.name,
  ].filter(Boolean);
  const candidates = new Set();

  for (const candidate of rawCandidates) {
    const normalized = normalizePathToken(candidate);
    const stripped = stripUnitreePrefix(normalized);
    candidates.add(normalized);
    candidates.add(stripped);
    candidates.add(`${UNITREE_USDA_PREFIX}${stripped}`);
  }

  return [...candidates];
}

function buildTruthStageIndex(truthReport) {
  const index = new Map();

  for (const [key, value] of Object.entries(truthReport || {})) {
    const normalized = normalizePathToken(key);
    const stripped = stripUnitreePrefix(normalized);
    index.set(normalized, { key, stage: value });
    index.set(stripped, { key, stage: value });
    index.set(`${UNITREE_USDA_PREFIX}${stripped}`, { key, stage: value });
  }

  return index;
}

function buildUniqueNameMap(entries, getName) {
  const map = new Map();
  const duplicates = new Set();

  for (const entry of entries) {
    const name = getName(entry);
    if (!name) {
      continue;
    }
    if (map.has(name)) {
      duplicates.add(name);
      continue;
    }
    map.set(name, entry);
  }

  return { duplicates: [...duplicates].sort(), map };
}

function normalizeColorTuple(value) {
  if (Array.isArray(value) && value.length >= 3) {
    const tuple = [Number(value[0]), Number(value[1]), Number(value[2])];
    return tuple.every(Number.isFinite) ? tuple : null;
  }

  if (value && typeof value === 'object') {
    const tuple = [Number(value.r ?? value.x), Number(value.g ?? value.y), Number(value.b ?? value.z)];
    return tuple.every(Number.isFinite) ? tuple : null;
  }

  if (typeof value === 'string') {
    const match = value.trim().match(/^#?([0-9a-f]{6})(?:[0-9a-f]{2})?$/i);
    if (!match) {
      return null;
    }
    return [0, 2, 4].map((offset) => Number.parseInt(match[1].slice(offset, offset + 2), 16) / 255);
  }

  return null;
}

function colorMaxChannelDistance(left, right) {
  if (!left && !right) {
    return 0;
  }
  if (!left || !right) {
    return Number.POSITIVE_INFINITY;
  }
  return Math.max(
    Math.abs(left[0] - right[0]),
    Math.abs(left[1] - right[1]),
    Math.abs(left[2] - right[2]),
  );
}

function materialSignatureDistance(left, right) {
  if (left.textured !== right.textured) {
    return Number.POSITIVE_INFINITY;
  }
  return colorMaxChannelDistance(left.color, right.color);
}

function materialSignatureKey(signature) {
  const colorKey = signature.color
    ? signature.color.map((entry) => Number(entry).toFixed(6)).join(',')
    : 'none';
  return `${signature.textured ? 1 : 0}:${colorKey}`;
}

function uniqueMaterialSignatures(signatures) {
  const map = new Map();
  for (const signature of signatures) {
    map.set(materialSignatureKey(signature), signature);
  }
  return [...map.values()];
}

function normalizeTruthMaterialSignature(value) {
  if (!value || typeof value !== 'object') {
    return null;
  }
  return {
    color: normalizeColorTuple(value.color),
    textured:
      typeof value.textured === 'boolean'
        ? value.textured
        : String(value.source || '').toLowerCase().includes('texture'),
  };
}

function getTruthMaterialSignatures(materialStage) {
  const visibleAppearanceSignatures = Array.isArray(materialStage?.visibleAppearanceSignatures)
    ? materialStage.visibleAppearanceSignatures
    : null;
  if (visibleAppearanceSignatures) {
    return uniqueMaterialSignatures(
      visibleAppearanceSignatures
        .map(normalizeTruthMaterialSignature)
        .filter((entry) => Boolean(entry)),
    );
  }

  const colors = Array.isArray(materialStage?.visibleMaterialColors)
    ? materialStage.visibleMaterialColors
    : [];
  return uniqueMaterialSignatures(
    colors
      .map((entry) => normalizeColorTuple(entry))
      .filter((entry) => Boolean(entry))
      .map((color) => ({ color, textured: false })),
  );
}

function normalizeBrowserMaterialSignature(material) {
  if (!material || typeof material !== 'object') {
    return null;
  }
  const color =
    normalizeColorTuple(material.colorTuple) ||
    normalizeColorTuple(material.authoredColorTuple) ||
    normalizeColorTuple(material.color) ||
    normalizeColorTuple(material.authoredColor);
  const textured =
    material.textured === true ||
    material.hasTexture === true ||
    Number(material.textureCount || 0) > 0 ||
    (Array.isArray(material.texturePaths) && material.texturePaths.length > 0);
  if (!color && !textured) {
    return null;
  }
  return { color, textured };
}

function isInformativeRuntimeMaterial(material) {
  if (!material || typeof material !== 'object') {
    return false;
  }
  return (
    String(material.name || '').trim().length > 0 ||
    material.hasTexture === true ||
    material.textured === true ||
    Number(material.textureCount || 0) > 0 ||
    (Array.isArray(material.texturePaths) && material.texturePaths.length > 0)
  );
}

function getBrowserMaterialSignatures(result) {
  const meshes = Array.isArray(result?.selectedUsdVisualMaterialSummary?.meshes)
    ? result.selectedUsdVisualMaterialSummary.meshes
    : [];
  const stageSignatures = uniqueMaterialSignatures(
    meshes.flatMap((mesh) =>
      (Array.isArray(mesh?.materials) ? mesh.materials : [])
        .map(normalizeBrowserMaterialSignature)
        .filter((entry) => Boolean(entry)),
    ),
  );
  if (stageSignatures.length > 0) {
    return stageSignatures;
  }

  const runtimeMeshes = Array.isArray(result?.snapshot?.runtime?.visualMeshes)
    ? result.snapshot.runtime.visualMeshes
    : [];
  return uniqueMaterialSignatures(
    runtimeMeshes.flatMap((mesh) =>
      (Array.isArray(mesh?.materials) ? mesh.materials : [])
        .filter((material) => isInformativeRuntimeMaterial(material))
        .map(normalizeBrowserMaterialSignature)
        .filter((entry) => Boolean(entry)),
    ),
  );
}

function compareMaterialSignatures(browserSignatures, truthSignatures, tolerance) {
  const remainingTruth = [...truthSignatures];
  const unmatchedBrowser = [];

  for (const browserSignature of browserSignatures) {
    let bestIndex = -1;
    let bestDistance = Number.POSITIVE_INFINITY;
    remainingTruth.forEach((truthSignature, index) => {
      const distance = materialSignatureDistance(browserSignature, truthSignature);
      if (distance < bestDistance) {
        bestIndex = index;
        bestDistance = distance;
      }
    });

    if (bestIndex >= 0 && bestDistance <= tolerance) {
      remainingTruth.splice(bestIndex, 1);
    } else {
      unmatchedBrowser.push(browserSignature);
    }
  }

  return {
    unmatchedBrowser,
    unmatchedTruth: remainingTruth,
  };
}

function estimateRuntimeWorldPositionOffset(truthBodies, browserRuntimeNameMap) {
  const deltas = [];
  for (const truthBody of truthBodies) {
    const linkName = getTruthBodyName(truthBody);
    const browserRuntimeLink = browserRuntimeNameMap.map.get(linkName);
    const browserPosition = getBrowserRuntimeLinkWorldPosition(browserRuntimeLink);
    const truthPosition = getTruthBodyWorldPosition(truthBody);
    if (browserPosition && truthPosition) {
      deltas.push(subtractVector3(browserPosition, truthPosition));
    }
  }

  if (deltas.length === 0) {
    return {
      offset: [0, 0, 0],
      sampleCount: 0,
    };
  }

  return {
    offset: [0, 1, 2].map((index) => median(deltas.map((entry) => entry[index]))),
    sampleCount: deltas.length,
  };
}

function normalizeModelFilters(modelFilters) {
  return new Set((modelFilters || []).map((entry) => stripUnitreePrefix(entry)));
}

function shouldIncludeResult(result, modelFilterSet) {
  if (!modelFilterSet || modelFilterSet.size === 0) {
    return true;
  }

  const candidates = getTruthCandidatesForResult(result).map((entry) => stripUnitreePrefix(entry));
  return candidates.some((candidate) => modelFilterSet.has(candidate));
}

export function compareUnitreeRosUsdaBrowserPhysics({
  browserReport,
  truthReport,
  materialTruthReport = null,
  massTolerance = DEFAULT_MASS_TOLERANCE,
  comTolerance = DEFAULT_COM_TOLERANCE,
  inertiaTolerance = DEFAULT_INERTIA_TOLERANCE,
  principalAxesTolerance = DEFAULT_PRINCIPAL_AXES_TOLERANCE,
  jointFrameTolerance = DEFAULT_JOINT_FRAME_TOLERANCE,
  linkPositionTolerance = DEFAULT_LINK_POSITION_TOLERANCE,
  linkOrientationTolerance = DEFAULT_LINK_ORIENTATION_TOLERANCE,
  worldPositionTolerance,
  materialColorTolerance = DEFAULT_MATERIAL_COLOR_TOLERANCE,
  modelFilters = [],
  maxFailureSamples = 32,
} = {}) {
  const resolvedWorldPositionTolerance = worldPositionTolerance ?? linkPositionTolerance;
  const results = Array.isArray(browserReport?.results) ? browserReport.results : [];
  const truthIndex = buildTruthStageIndex(truthReport);
  const materialTruthIndex = materialTruthReport ? buildTruthStageIndex(materialTruthReport) : null;
  const modelFilterSet = normalizeModelFilters(modelFilters);
  const perModel = [];
  const failures = [];
  const summary = {
    models: 0,
    matchedLinks: 0,
    browserLinks: 0,
    truthBodies: 0,
    browserJoints: 0,
    nativeJoints: 0,
    truthJoints: 0,
    matchedJoints: 0,
    browserLinkPoses: 0,
    matchedLinkPoses: 0,
    browserRuntimeLinks: 0,
    matchedRuntimeLinkPositions: 0,
    browserCollisions: 0,
    truthCollisions: 0,
    matchedCollisionBodies: 0,
    browserMaterialAppearances: 0,
    truthMaterialAppearances: 0,
    browserTexturedMaterialAppearances: 0,
    truthTexturedMaterialAppearances: 0,
    maxMassErr: 0,
    maxComErr: 0,
    maxInertiaErr: 0,
    maxPrincipalAxesErr: 0,
    maxJointFrameErr: 0,
    maxNativeJointFrameErr: 0,
    maxLinkPositionErr: 0,
    maxLinkOrientationErr: 0,
    maxWorldPositionErr: 0,
    maxCollisionCountDelta: 0,
    missingLinks: 0,
    extraLinks: 0,
    missingBrowserLinkPoses: 0,
    missingBrowserWorldPositions: 0,
    missingTruthWorldPositions: 0,
    missingBrowserJoints: 0,
    missingNativeJoints: 0,
    skippedExtraVisualLinks: 0,
    skippedBrowserRootJoints: 0,
    skippedNativeRootJoints: 0,
    missingMaterialTruthStages: 0,
    massMismatches: 0,
    comMismatches: 0,
    inertiaMismatches: 0,
    principalAxesMismatches: 0,
    linkPositionMismatches: 0,
    linkOrientationMismatches: 0,
    worldPositionMismatches: 0,
    collisionCountMismatches: 0,
    materialAppearanceMismatches: 0,
    jointFrameMismatches: 0,
    nativeJointFrameMismatches: 0,
    duplicateBrowserNames: 0,
    duplicateBrowserLinkPoseNames: 0,
    duplicateBrowserWorldTransformNames: 0,
    duplicateTruthNames: 0,
    duplicateBrowserJointNames: 0,
    duplicateNativeJointNames: 0,
    duplicateTruthJointNames: 0,
    missingTruthStages: 0,
    worstMass: null,
    worstCom: null,
    worstInertia: null,
    worstPrincipalAxes: null,
    worstLinkPosition: null,
    worstLinkOrientation: null,
    worstWorldPosition: null,
    worstCollisionCount: null,
    worstMaterialAppearance: null,
    worstJointFrame: null,
    worstNativeJointFrame: null,
  };

  const addFailure = (failure) => {
    failures.push(failure);
  };

  for (const result of results) {
    if (!shouldIncludeResult(result, modelFilterSet)) {
      continue;
    }

    const modelKey = getResultModelKey(result);
    const truthEntry = getTruthCandidatesForResult(result)
      .map((candidate) => truthIndex.get(candidate))
      .find(Boolean);

    summary.models += 1;

    if (!truthEntry?.stage) {
      summary.missingTruthStages += 1;
      addFailure({
        type: 'missing-truth-stage',
        model: modelKey,
        candidates: getTruthCandidatesForResult(result),
      });
      perModel.push({
        model: modelKey,
        pass: false,
        browserLinks: Number(result?.snapshot?.store?.linkCount ?? 0),
        truthBodies: 0,
        matchedLinks: 0,
        browserJoints: Number(result?.snapshot?.store?.jointCount ?? 0),
        nativeJoints: 0,
        truthJoints: 0,
        matchedJoints: 0,
        browserLinkPoses: 0,
        matchedLinkPoses: 0,
        browserRuntimeLinks: 0,
        matchedRuntimeLinkPositions: 0,
        runtimeWorldPositionOffset: [0, 0, 0],
        runtimeWorldPositionOffsetSampleCount: 0,
        browserCollisions: 0,
        truthCollisions: 0,
        matchedCollisionBodies: 0,
        browserMaterialAppearances: 0,
        truthMaterialAppearances: 0,
        browserTexturedMaterialAppearances: 0,
        truthTexturedMaterialAppearances: 0,
        missingLinks: 0,
        extraLinks: 0,
        missingBrowserLinkPoses: 0,
        missingBrowserWorldPositions: 0,
        missingTruthWorldPositions: 0,
        missingBrowserJoints: 0,
        missingNativeJoints: 0,
        skippedExtraVisualLinks: 0,
        skippedBrowserRootJoints: 0,
        skippedNativeRootJoints: 0,
        missingMaterialTruthStages: 0,
        maxMassErr: 0,
        maxComErr: 0,
        maxInertiaErr: 0,
        maxPrincipalAxesErr: 0,
        maxJointFrameErr: 0,
        maxNativeJointFrameErr: 0,
        maxLinkPositionErr: 0,
        maxLinkOrientationErr: 0,
        maxWorldPositionErr: 0,
        maxCollisionCountDelta: 0,
        collisionCountMismatches: 0,
        materialAppearanceMismatches: 0,
      });
      continue;
    }

    const truthStage = truthEntry.stage;
    if (truthStage.open_ok === false) {
      addFailure({
        type: 'truth-stage-open-failed',
        model: modelKey,
        truthKey: truthEntry.key,
      });
    }

    const browserLinks = Array.isArray(result?.snapshot?.store?.links)
      ? result.snapshot.store.links
      : [];
    const browserJoints = Array.isArray(result?.snapshot?.store?.joints)
      ? result.snapshot.store.joints
      : [];
    const nativeJoints = Array.isArray(result?.selectedUsdSceneSummary?.robotMetadata?.joints)
      ? result.selectedUsdSceneSummary.robotMetadata.joints
      : [];
    const browserLinkPoses = Array.isArray(result?.selectedUsdSceneSummary?.linkPoses?.storeLinks)
      ? result.selectedUsdSceneSummary.linkPoses.storeLinks
      : [];
    const browserRuntimeLinks = Array.isArray(result?.runtimeSceneTransforms?.links)
      ? result.runtimeSceneTransforms.links
      : [];
    const truthBodies = Object.values(truthStage.rigidBodies || {});
    const truthJoints = Object.values(truthStage.joints || truthStage.physicsJoints || {});
    const browserNameMap = buildUniqueNameMap(browserLinks, getBrowserLinkName);
    const browserLinkPoseNameMap = buildUniqueNameMap(browserLinkPoses, getBrowserLinkPoseName);
    const browserRuntimeNameMap = buildUniqueNameMap(
      browserRuntimeLinks,
      getBrowserRuntimeLinkName,
    );
    const truthNameMap = buildUniqueNameMap(truthBodies, getTruthBodyName);
    const browserJointNameMap = buildUniqueNameMap(browserJoints, getBrowserJointName);
    const nativeJointNameMap = buildUniqueNameMap(nativeJoints, getNativeJointName);
    const truthJointNameMap = buildUniqueNameMap(truthJoints, getTruthJointName);
    const modelStats = {
      model: modelKey,
      truthKey: truthEntry.key,
      pass: true,
      browserLinks: browserLinks.length,
      truthBodies: truthBodies.length,
      browserJoints: browserJoints.length,
      nativeJoints: nativeJoints.length,
      truthJoints: truthJoints.length,
      browserLinkPoses: browserLinkPoses.length,
      browserRuntimeLinks: browserRuntimeLinks.length,
      runtimeWorldPositionOffset: [0, 0, 0],
      runtimeWorldPositionOffsetSampleCount: 0,
      browserCollisions: 0,
      truthCollisions: 0,
      matchedCollisionBodies: 0,
      browserMaterialAppearances: 0,
      truthMaterialAppearances: 0,
      browserTexturedMaterialAppearances: 0,
      truthTexturedMaterialAppearances: 0,
      matchedLinks: 0,
      matchedJoints: 0,
      matchedLinkPoses: 0,
      matchedRuntimeLinkPositions: 0,
      missingLinks: 0,
      extraLinks: 0,
      missingBrowserLinkPoses: 0,
      missingBrowserWorldPositions: 0,
      missingTruthWorldPositions: 0,
      missingBrowserJoints: 0,
      missingNativeJoints: 0,
      skippedExtraVisualLinks: 0,
      skippedBrowserRootJoints: 0,
      skippedNativeRootJoints: 0,
      missingMaterialTruthStages: 0,
      massMismatches: 0,
      comMismatches: 0,
      inertiaMismatches: 0,
      principalAxesMismatches: 0,
      linkPositionMismatches: 0,
      linkOrientationMismatches: 0,
      worldPositionMismatches: 0,
      collisionCountMismatches: 0,
      materialAppearanceMismatches: 0,
      jointFrameMismatches: 0,
      nativeJointFrameMismatches: 0,
      duplicateBrowserNames: browserNameMap.duplicates.length,
      duplicateBrowserLinkPoseNames: browserLinkPoseNameMap.duplicates.length,
      duplicateBrowserWorldTransformNames: browserRuntimeNameMap.duplicates.length,
      duplicateTruthNames: truthNameMap.duplicates.length,
      duplicateBrowserJointNames: browserJointNameMap.duplicates.length,
      duplicateNativeJointNames: nativeJointNameMap.duplicates.length,
      duplicateTruthJointNames: truthJointNameMap.duplicates.length,
      maxMassErr: 0,
      maxComErr: 0,
      maxInertiaErr: 0,
      maxPrincipalAxesErr: 0,
      maxJointFrameErr: 0,
      maxNativeJointFrameErr: 0,
      maxLinkPositionErr: 0,
      maxLinkOrientationErr: 0,
      maxWorldPositionErr: 0,
      maxCollisionCountDelta: 0,
      worstMass: null,
      worstCom: null,
      worstInertia: null,
      worstPrincipalAxes: null,
      worstLinkPosition: null,
      worstLinkOrientation: null,
      worstWorldPosition: null,
      worstCollisionCount: null,
      worstMaterialAppearance: null,
      worstJointFrame: null,
      worstNativeJointFrame: null,
    };

    const browserCollisionCountByName = buildBrowserCollisionCountByName(result, browserLinks);
    modelStats.browserCollisions = Array.from(browserCollisionCountByName.values()).reduce(
      (sum, value) => sum + value,
      0,
    );
    modelStats.truthCollisions = truthBodies.reduce(
      (sum, body) => sum + Math.max(0, Number(body?.collisionCount) || 0),
      0,
    );
    const runtimeOffsetEstimate = estimateRuntimeWorldPositionOffset(
      truthBodies,
      browserRuntimeNameMap,
    );
    modelStats.runtimeWorldPositionOffset = runtimeOffsetEstimate.offset;
    modelStats.runtimeWorldPositionOffsetSampleCount = runtimeOffsetEstimate.sampleCount;

    let materialTruthStage = null;
    if (materialTruthIndex) {
      const materialTruthEntry = getTruthCandidatesForResult(result)
        .map((candidate) => materialTruthIndex.get(candidate))
        .find(Boolean);
      if (materialTruthEntry?.stage) {
        materialTruthStage = materialTruthEntry.stage;
      } else {
        modelStats.missingMaterialTruthStages += 1;
        addFailure({
          type: 'missing-material-truth-stage',
          model: modelKey,
          candidates: getTruthCandidatesForResult(result),
        });
      }
    }

    for (const duplicateName of browserNameMap.duplicates) {
      addFailure({ type: 'duplicate-browser-link-name', model: modelKey, link: duplicateName });
    }
    for (const duplicateName of browserLinkPoseNameMap.duplicates) {
      addFailure({ type: 'duplicate-browser-link-pose-name', model: modelKey, link: duplicateName });
    }
    for (const duplicateName of browserRuntimeNameMap.duplicates) {
      addFailure({
        type: 'duplicate-browser-world-transform-link-name',
        model: modelKey,
        link: duplicateName,
      });
    }
    for (const duplicateName of truthNameMap.duplicates) {
      addFailure({ type: 'duplicate-truth-body-name', model: modelKey, link: duplicateName });
    }
    for (const duplicateName of browserJointNameMap.duplicates) {
      addFailure({ type: 'duplicate-browser-joint-name', model: modelKey, joint: duplicateName });
    }
    for (const duplicateName of nativeJointNameMap.duplicates) {
      addFailure({ type: 'duplicate-native-joint-name', model: modelKey, joint: duplicateName });
    }
    for (const duplicateName of truthJointNameMap.duplicates) {
      addFailure({ type: 'duplicate-truth-joint-name', model: modelKey, joint: duplicateName });
    }

    if (materialTruthStage) {
      const browserMaterialSignatures = getBrowserMaterialSignatures(result);
      const truthMaterialSignatures = getTruthMaterialSignatures(materialTruthStage);
      modelStats.browserMaterialAppearances = browserMaterialSignatures.length;
      modelStats.truthMaterialAppearances = truthMaterialSignatures.length;
      modelStats.browserTexturedMaterialAppearances = browserMaterialSignatures.filter(
        (signature) => signature.textured,
      ).length;
      modelStats.truthTexturedMaterialAppearances = truthMaterialSignatures.filter(
        (signature) => signature.textured,
      ).length;

      const materialComparison = compareMaterialSignatures(
        browserMaterialSignatures,
        truthMaterialSignatures,
        materialColorTolerance,
      );
      const materialMismatchCount =
        materialComparison.unmatchedBrowser.length + materialComparison.unmatchedTruth.length;
      if (materialMismatchCount > 0) {
        modelStats.materialAppearanceMismatches = materialMismatchCount;
        modelStats.worstMaterialAppearance = materialComparison;
        addFailure({
          type: 'material-appearance-mismatch',
          model: modelKey,
          browserMaterialAppearances: browserMaterialSignatures,
          truthMaterialAppearances: truthMaterialSignatures,
          unmatchedBrowser: materialComparison.unmatchedBrowser,
          unmatchedTruth: materialComparison.unmatchedTruth,
          tolerance: materialColorTolerance,
        });
      }
    }

    for (const truthBody of truthBodies) {
      const linkName = getTruthBodyName(truthBody);
      const browserLink = browserNameMap.map.get(linkName);
      if (!browserLink) {
        modelStats.missingLinks += 1;
        addFailure({
          type: 'missing-browser-link',
          model: modelKey,
          link: linkName,
          truthFullPath: truthBody.fullPath ?? null,
          truthMass: finiteNumberOrZero(truthBody.mass),
          truthCenterOfMass: vector3OrZero(truthBody.centerOfMass),
        });
        continue;
      }

      modelStats.matchedLinks += 1;
      modelStats.matchedCollisionBodies += 1;
      const browserCollisionCount = browserCollisionCountByName.get(linkName) || 0;
      const truthCollisionCount = Math.max(0, Number(truthBody?.collisionCount) || 0);
      const collisionCountDelta = Math.abs(browserCollisionCount - truthCollisionCount);
      if (collisionCountDelta > modelStats.maxCollisionCountDelta) {
        modelStats.maxCollisionCountDelta = collisionCountDelta;
        modelStats.worstCollisionCount = {
          link: linkName,
          browserCollisionCount,
          truthCollisionCount,
          collisionCountDelta,
        };
      }
      if (collisionCountDelta > 0) {
        modelStats.collisionCountMismatches += 1;
        addFailure({
          type: 'collision-count-mismatch',
          model: modelKey,
          link: linkName,
          browserCollisionCount,
          truthCollisionCount,
        });
      }

      const browserLinkPose = browserLinkPoseNameMap.map.get(linkName);
      const truthWorldPose = getTruthBodyWorldPose(truthBody);
      if (!browserLinkPose) {
        modelStats.missingBrowserLinkPoses += 1;
        addFailure({
          type: 'missing-browser-link-pose',
          model: modelKey,
          link: linkName,
          truthFullPath: truthBody.fullPath ?? null,
          truthWorldPose,
        });
      } else {
        modelStats.matchedLinkPoses += 1;
        const browserWorldPose = getBrowserLinkWorldPose(browserLinkPose);
        const linkPositionErr = vectorDistance(browserWorldPose.position, truthWorldPose.position);
        if (linkPositionErr > modelStats.maxLinkPositionErr) {
          modelStats.maxLinkPositionErr = linkPositionErr;
          modelStats.worstLinkPosition = {
            link: linkName,
            browserPosition: browserWorldPose.position,
            truthPosition: truthWorldPose.position,
            linkPositionErr,
          };
        }
        if (linkPositionErr > linkPositionTolerance) {
          modelStats.linkPositionMismatches += 1;
          addFailure({
            type: 'link-position-mismatch',
            model: modelKey,
            link: linkName,
            browserPosition: browserWorldPose.position,
            truthPosition: truthWorldPose.position,
            linkPositionErr,
            tolerance: linkPositionTolerance,
          });
        }

        const linkOrientationErr = quaternionDistanceWxyz(
          browserWorldPose.orientationWxyz,
          truthWorldPose.orientationWxyz,
        );
        if (linkOrientationErr > modelStats.maxLinkOrientationErr) {
          modelStats.maxLinkOrientationErr = linkOrientationErr;
          modelStats.worstLinkOrientation = {
            link: linkName,
            browserOrientationWxyz: browserWorldPose.orientationWxyz,
            truthOrientationWxyz: truthWorldPose.orientationWxyz,
            linkOrientationErr,
          };
        }
        if (linkOrientationErr > linkOrientationTolerance) {
          modelStats.linkOrientationMismatches += 1;
          addFailure({
            type: 'link-orientation-mismatch',
            model: modelKey,
            link: linkName,
            browserOrientationWxyz: browserWorldPose.orientationWxyz,
            truthOrientationWxyz: truthWorldPose.orientationWxyz,
            linkOrientationErr,
            tolerance: linkOrientationTolerance,
          });
        }
      }

      if (browserRuntimeLinks.length > 0) {
        const browserRuntimeLink = browserRuntimeNameMap.map.get(linkName);
        const truthWorldPosition = getTruthBodyWorldPosition(truthBody);
        if (!browserRuntimeLink) {
          modelStats.missingBrowserWorldPositions += 1;
          addFailure({
            type: 'missing-browser-world-position',
            model: modelKey,
            link: linkName,
            truthFullPath: truthBody.fullPath ?? null,
          });
        } else {
          const browserWorldPosition = getBrowserRuntimeLinkWorldPosition(browserRuntimeLink);
          if (!browserWorldPosition) {
            modelStats.missingBrowserWorldPositions += 1;
            addFailure({
              type: 'missing-browser-world-position',
              model: modelKey,
              link: linkName,
              truthFullPath: truthBody.fullPath ?? null,
            });
          } else if (!truthWorldPosition) {
            modelStats.missingTruthWorldPositions += 1;
            addFailure({
              type: 'missing-truth-world-position',
              model: modelKey,
              link: linkName,
              truthFullPath: truthBody.fullPath ?? null,
            });
          } else {
            modelStats.matchedRuntimeLinkPositions += 1;
            const adjustedBrowserWorldPosition = subtractVector3(
              browserWorldPosition,
              modelStats.runtimeWorldPositionOffset,
            );
            const worldPositionErr = vectorDistance(
              adjustedBrowserWorldPosition,
              truthWorldPosition,
            );
            if (worldPositionErr > modelStats.maxWorldPositionErr) {
              modelStats.maxWorldPositionErr = worldPositionErr;
              modelStats.worstWorldPosition = {
                link: linkName,
                browserWorldPosition,
                adjustedBrowserWorldPosition,
                truthWorldPosition,
                runtimeWorldPositionOffset: modelStats.runtimeWorldPositionOffset,
                worldPositionErr,
              };
            }
            if (worldPositionErr > resolvedWorldPositionTolerance) {
              modelStats.worldPositionMismatches += 1;
              addFailure({
                type: 'world-position-mismatch',
                model: modelKey,
                link: linkName,
                browserWorldPosition,
                adjustedBrowserWorldPosition,
                truthWorldPosition,
                runtimeWorldPositionOffset: modelStats.runtimeWorldPositionOffset,
                worldPositionErr,
                browserHeight: adjustedBrowserWorldPosition[2],
                truthHeight: truthWorldPosition[2],
                heightErr: Math.abs(adjustedBrowserWorldPosition[2] - truthWorldPosition[2]),
                tolerance: resolvedWorldPositionTolerance,
              });
            }
          }
        }
      }

      const browserMass = finiteNumberOrZero(browserLink.mass);
      const truthMass = finiteNumberOrZero(truthBody.mass);
      const massErr = Math.abs(browserMass - truthMass);
      if (massErr > modelStats.maxMassErr) {
        modelStats.maxMassErr = massErr;
        modelStats.worstMass = {
          link: linkName,
          browserMass,
          truthMass,
          massErr,
        };
      }
      if (massErr > massTolerance) {
        modelStats.massMismatches += 1;
        addFailure({
          type: 'mass-mismatch',
          model: modelKey,
          link: linkName,
          browserMass,
          truthMass,
          massErr,
          tolerance: massTolerance,
        });
      }

      const browserCenterOfMass = getBrowserLinkCenterOfMass(browserLink);
      const truthCenterOfMass = vector3OrZero(truthBody.centerOfMass);
      const comErr = vectorDistance(browserCenterOfMass, truthCenterOfMass);
      if (comErr > modelStats.maxComErr) {
        modelStats.maxComErr = comErr;
        modelStats.worstCom = {
          link: linkName,
          browserCenterOfMass,
          truthCenterOfMass,
          comErr,
        };
      }
      if (comErr > comTolerance) {
        modelStats.comMismatches += 1;
        addFailure({
          type: 'center-of-mass-mismatch',
          model: modelKey,
          link: linkName,
          browserCenterOfMass,
          truthCenterOfMass,
          comErr,
          tolerance: comTolerance,
        });
      }

      const browserDiagonalInertia = getBrowserLinkDiagonalInertia(browserLink);
      const truthDiagonalInertia = vector3OrZero(truthBody.diagonalInertia);
      const inertiaErr = vectorDistance(browserDiagonalInertia, truthDiagonalInertia);
      if (inertiaErr > modelStats.maxInertiaErr) {
        modelStats.maxInertiaErr = inertiaErr;
        modelStats.worstInertia = {
          link: linkName,
          browserDiagonalInertia,
          truthDiagonalInertia,
          inertiaErr,
        };
      }
      if (inertiaErr > inertiaTolerance) {
        modelStats.inertiaMismatches += 1;
        addFailure({
          type: 'diagonal-inertia-mismatch',
          model: modelKey,
          link: linkName,
          browserDiagonalInertia,
          truthDiagonalInertia,
          inertiaErr,
          tolerance: inertiaTolerance,
        });
      }

      const browserPrincipalAxes = getBrowserLinkPrincipalAxes(browserLink);
      const truthPrincipalAxes = quaternionWxyzOrIdentity(truthBody.principalAxes);
      const principalAxesErr = quaternionDistanceWxyz(browserPrincipalAxes, truthPrincipalAxes);
      if (principalAxesErr > modelStats.maxPrincipalAxesErr) {
        modelStats.maxPrincipalAxesErr = principalAxesErr;
        modelStats.worstPrincipalAxes = {
          link: linkName,
          browserPrincipalAxes,
          truthPrincipalAxes,
          principalAxesErr,
        };
      }
      if (principalAxesErr > principalAxesTolerance) {
        modelStats.principalAxesMismatches += 1;
        addFailure({
          type: 'principal-axes-mismatch',
          model: modelKey,
          link: linkName,
          browserPrincipalAxes,
          truthPrincipalAxes,
          principalAxesErr,
          tolerance: principalAxesTolerance,
        });
      }
    }

    for (const browserLink of browserLinks) {
      const linkName = getBrowserLinkName(browserLink);
      if (!truthNameMap.map.has(linkName)) {
        if (isSyntheticBrowserVisualLink(browserLink)) {
          modelStats.skippedExtraVisualLinks += 1;
          continue;
        }
        modelStats.extraLinks += 1;
        addFailure({
          type: 'extra-browser-link',
          model: modelKey,
          link: linkName,
          browserMass: finiteNumberOrZero(browserLink.mass),
          browserCenterOfMass: getBrowserLinkCenterOfMass(browserLink),
        });
      }
    }

    for (const truthJoint of truthJoints) {
      const jointName = getTruthJointName(truthJoint);
      if (!jointName) {
        continue;
      }

      const browserJoint = browserJointNameMap.map.get(jointName);
      const nativeJoint = nativeJointNameMap.map.get(jointName);
      const truthFrame = getTruthJointFrame(truthJoint);

      if (!browserJoint) {
        if (isParentlessRootFixedJoint(truthJoint)) {
          modelStats.skippedBrowserRootJoints += 1;
        } else {
          modelStats.missingBrowserJoints += 1;
          addFailure({
            type: 'missing-browser-joint',
            model: modelKey,
            joint: jointName,
            truthFullPath: truthJoint.fullPath ?? null,
            truthFrame,
          });
        }
      } else {
        modelStats.matchedJoints += 1;
        compareJointFrame({
          addFailure,
          modelKey,
          modelStats,
          jointName,
          observedFrame: getBrowserJointFrame(browserJoint),
          truthFrame,
          tolerance: jointFrameTolerance,
          sourceLabel: 'store',
          mismatchCounterKey: 'jointFrameMismatches',
          maxErrKey: 'maxJointFrameErr',
          worstKey: 'worstJointFrame',
        });
      }

      if (!nativeJoint) {
        if (isParentlessRootFixedJoint(truthJoint)) {
          modelStats.skippedNativeRootJoints += 1;
        } else {
          modelStats.missingNativeJoints += 1;
          addFailure({
            type: 'missing-native-joint',
            model: modelKey,
            joint: jointName,
            truthFullPath: truthJoint.fullPath ?? null,
            truthFrame,
          });
        }
      } else {
        compareJointFrame({
          addFailure,
          modelKey,
          modelStats,
          jointName,
          observedFrame: getNativeJointFrame(nativeJoint),
          truthFrame,
          tolerance: jointFrameTolerance,
          sourceLabel: 'native',
          mismatchCounterKey: 'nativeJointFrameMismatches',
          maxErrKey: 'maxNativeJointFrameErr',
          worstKey: 'worstNativeJointFrame',
        });
      }
    }

    modelStats.pass =
      modelStats.missingLinks === 0 &&
      modelStats.extraLinks === 0 &&
      modelStats.missingBrowserLinkPoses === 0 &&
      modelStats.missingBrowserJoints === 0 &&
      modelStats.missingNativeJoints === 0 &&
      modelStats.missingMaterialTruthStages === 0 &&
      modelStats.massMismatches === 0 &&
      modelStats.comMismatches === 0 &&
      modelStats.inertiaMismatches === 0 &&
      modelStats.principalAxesMismatches === 0 &&
      modelStats.linkPositionMismatches === 0 &&
      modelStats.linkOrientationMismatches === 0 &&
      modelStats.worldPositionMismatches === 0 &&
      modelStats.collisionCountMismatches === 0 &&
      modelStats.materialAppearanceMismatches === 0 &&
      modelStats.missingBrowserWorldPositions === 0 &&
      modelStats.missingTruthWorldPositions === 0 &&
      modelStats.jointFrameMismatches === 0 &&
      modelStats.nativeJointFrameMismatches === 0 &&
      modelStats.duplicateBrowserNames === 0 &&
      modelStats.duplicateBrowserLinkPoseNames === 0 &&
      modelStats.duplicateBrowserWorldTransformNames === 0 &&
      modelStats.duplicateTruthNames === 0 &&
      modelStats.duplicateBrowserJointNames === 0 &&
      modelStats.duplicateNativeJointNames === 0 &&
      modelStats.duplicateTruthJointNames === 0 &&
      truthStage.open_ok !== false;

    summary.matchedLinks += modelStats.matchedLinks;
    summary.browserLinks += modelStats.browserLinks;
    summary.truthBodies += modelStats.truthBodies;
    summary.browserLinkPoses += modelStats.browserLinkPoses;
    summary.matchedLinkPoses += modelStats.matchedLinkPoses;
    summary.browserRuntimeLinks += modelStats.browserRuntimeLinks;
    summary.matchedRuntimeLinkPositions += modelStats.matchedRuntimeLinkPositions;
    summary.browserCollisions += modelStats.browserCollisions;
    summary.truthCollisions += modelStats.truthCollisions;
    summary.matchedCollisionBodies += modelStats.matchedCollisionBodies;
    summary.browserMaterialAppearances += modelStats.browserMaterialAppearances;
    summary.truthMaterialAppearances += modelStats.truthMaterialAppearances;
    summary.browserTexturedMaterialAppearances += modelStats.browserTexturedMaterialAppearances;
    summary.truthTexturedMaterialAppearances += modelStats.truthTexturedMaterialAppearances;
    summary.browserJoints += modelStats.browserJoints;
    summary.nativeJoints += modelStats.nativeJoints;
    summary.truthJoints += modelStats.truthJoints;
    summary.matchedJoints += modelStats.matchedJoints;
    summary.missingLinks += modelStats.missingLinks;
    summary.extraLinks += modelStats.extraLinks;
    summary.missingBrowserLinkPoses += modelStats.missingBrowserLinkPoses;
    summary.missingBrowserWorldPositions += modelStats.missingBrowserWorldPositions;
    summary.missingTruthWorldPositions += modelStats.missingTruthWorldPositions;
    summary.missingBrowserJoints += modelStats.missingBrowserJoints;
    summary.missingNativeJoints += modelStats.missingNativeJoints;
    summary.skippedExtraVisualLinks += modelStats.skippedExtraVisualLinks;
    summary.skippedBrowserRootJoints += modelStats.skippedBrowserRootJoints;
    summary.skippedNativeRootJoints += modelStats.skippedNativeRootJoints;
    summary.missingMaterialTruthStages += modelStats.missingMaterialTruthStages;
    summary.massMismatches += modelStats.massMismatches;
    summary.comMismatches += modelStats.comMismatches;
    summary.inertiaMismatches += modelStats.inertiaMismatches;
    summary.principalAxesMismatches += modelStats.principalAxesMismatches;
    summary.linkPositionMismatches += modelStats.linkPositionMismatches;
    summary.linkOrientationMismatches += modelStats.linkOrientationMismatches;
    summary.worldPositionMismatches += modelStats.worldPositionMismatches;
    summary.collisionCountMismatches += modelStats.collisionCountMismatches;
    summary.materialAppearanceMismatches += modelStats.materialAppearanceMismatches;
    summary.jointFrameMismatches += modelStats.jointFrameMismatches;
    summary.nativeJointFrameMismatches += modelStats.nativeJointFrameMismatches;
    summary.duplicateBrowserNames += modelStats.duplicateBrowserNames;
    summary.duplicateBrowserLinkPoseNames += modelStats.duplicateBrowserLinkPoseNames;
    summary.duplicateBrowserWorldTransformNames += modelStats.duplicateBrowserWorldTransformNames;
    summary.duplicateTruthNames += modelStats.duplicateTruthNames;
    summary.duplicateBrowserJointNames += modelStats.duplicateBrowserJointNames;
    summary.duplicateNativeJointNames += modelStats.duplicateNativeJointNames;
    summary.duplicateTruthJointNames += modelStats.duplicateTruthJointNames;
    if (modelStats.maxMassErr > summary.maxMassErr) {
      summary.maxMassErr = modelStats.maxMassErr;
      summary.worstMass = modelStats.worstMass
        ? { model: modelKey, ...modelStats.worstMass }
        : null;
    }
    if (modelStats.maxComErr > summary.maxComErr) {
      summary.maxComErr = modelStats.maxComErr;
      summary.worstCom = modelStats.worstCom ? { model: modelKey, ...modelStats.worstCom } : null;
    }
    if (modelStats.maxInertiaErr > summary.maxInertiaErr) {
      summary.maxInertiaErr = modelStats.maxInertiaErr;
      summary.worstInertia = modelStats.worstInertia
        ? { model: modelKey, ...modelStats.worstInertia }
        : null;
    }
    if (modelStats.maxPrincipalAxesErr > summary.maxPrincipalAxesErr) {
      summary.maxPrincipalAxesErr = modelStats.maxPrincipalAxesErr;
      summary.worstPrincipalAxes = modelStats.worstPrincipalAxes
        ? { model: modelKey, ...modelStats.worstPrincipalAxes }
        : null;
    }
    if (modelStats.maxLinkPositionErr > summary.maxLinkPositionErr) {
      summary.maxLinkPositionErr = modelStats.maxLinkPositionErr;
      summary.worstLinkPosition = modelStats.worstLinkPosition
        ? { model: modelKey, ...modelStats.worstLinkPosition }
        : null;
    }
    if (modelStats.maxLinkOrientationErr > summary.maxLinkOrientationErr) {
      summary.maxLinkOrientationErr = modelStats.maxLinkOrientationErr;
      summary.worstLinkOrientation = modelStats.worstLinkOrientation
        ? { model: modelKey, ...modelStats.worstLinkOrientation }
        : null;
    }
    if (modelStats.maxWorldPositionErr > summary.maxWorldPositionErr) {
      summary.maxWorldPositionErr = modelStats.maxWorldPositionErr;
      summary.worstWorldPosition = modelStats.worstWorldPosition
        ? { model: modelKey, ...modelStats.worstWorldPosition }
        : null;
    }
    if (modelStats.maxCollisionCountDelta > summary.maxCollisionCountDelta) {
      summary.maxCollisionCountDelta = modelStats.maxCollisionCountDelta;
      summary.worstCollisionCount = modelStats.worstCollisionCount
        ? { model: modelKey, ...modelStats.worstCollisionCount }
        : null;
    }
    if (!summary.worstMaterialAppearance && modelStats.worstMaterialAppearance) {
      summary.worstMaterialAppearance = {
        model: modelKey,
        ...modelStats.worstMaterialAppearance,
      };
    }
    if (modelStats.maxJointFrameErr > summary.maxJointFrameErr) {
      summary.maxJointFrameErr = modelStats.maxJointFrameErr;
      summary.worstJointFrame = modelStats.worstJointFrame
        ? { model: modelKey, ...modelStats.worstJointFrame }
        : null;
    }
    if (modelStats.maxNativeJointFrameErr > summary.maxNativeJointFrameErr) {
      summary.maxNativeJointFrameErr = modelStats.maxNativeJointFrameErr;
      summary.worstNativeJointFrame = modelStats.worstNativeJointFrame
        ? { model: modelKey, ...modelStats.worstNativeJointFrame }
        : null;
    }

    perModel.push(modelStats);
  }

  if (summary.models === 0) {
    addFailure({
      type: 'no-browser-results',
      message: 'No browser report results matched the requested filters.',
    });
  }

  const pass = failures.length === 0;
  return {
    pass,
    summary: {
      ...summary,
      pass,
      failureCount: failures.length,
      massTolerance,
      comTolerance,
      inertiaTolerance,
      principalAxesTolerance,
      jointFrameTolerance,
      linkPositionTolerance,
      linkOrientationTolerance,
      worldPositionTolerance: resolvedWorldPositionTolerance,
      materialColorTolerance,
    },
    perModel,
    failures: failures.slice(0, maxFailureSamples),
    omittedFailureCount: Math.max(0, failures.length - maxFailureSamples),
  };
}

function printUsage() {
  console.log(`Usage:
  node scripts/test/truth/compare_unitree_ros_usda_browser_physics.mjs [options]

Options:
  --browser-report <path>  Browser regression JSON. Default: ${DEFAULT_BROWSER_REPORT_PATH}
  --truth <path>           IsaacLab/IsaacSim physics JSON. Default: ${DEFAULT_TRUTH_PATH}
  --material-truth <path>  Optional IsaacLab/IsaacSim material JSON.
  --output <path>          Comparison JSON output. Default: ${DEFAULT_OUTPUT_PATH}
  --model <filter>         Restrict to a model path. Repeatable.
  --mass-tolerance <n>     Absolute mass tolerance. Default: ${DEFAULT_MASS_TOLERANCE}
  --com-tolerance <n>      Euclidean COM tolerance. Default: ${DEFAULT_COM_TOLERANCE}
  --inertia-tolerance <n>  Euclidean diagonal inertia tolerance. Default: ${DEFAULT_INERTIA_TOLERANCE}
  --principal-axes-tolerance <n>
                           Quaternion principal axes tolerance. Default: ${DEFAULT_PRINCIPAL_AXES_TOLERANCE}
  --joint-frame-tolerance <n>
                           Joint local frame tolerance. Default: ${DEFAULT_JOINT_FRAME_TOLERANCE}
  --link-position-tolerance <n>
                           Store link world-position tolerance. Default: ${DEFAULT_LINK_POSITION_TOLERANCE}
  --link-orientation-tolerance <n>
                           Store link world-orientation quaternion tolerance. Default: ${DEFAULT_LINK_ORIENTATION_TOLERANCE}
  --world-position-tolerance <n>
                           Runtime link world-position tolerance. Default: ${DEFAULT_WORLD_POSITION_TOLERANCE}
  --material-color-tolerance <n>
                           RGB max-channel material tolerance. Default: ${DEFAULT_MATERIAL_COLOR_TOLERANCE}
  --max-failures <n>       Failure samples to include in output. Default: 32
  --help                   Show this help message.
`);
}

function parseArgs(argv) {
  const options = {
    browserReportPath: DEFAULT_BROWSER_REPORT_PATH,
    truthPath: DEFAULT_TRUTH_PATH,
    materialTruthPath: null,
    outputPath: DEFAULT_OUTPUT_PATH,
    massTolerance: DEFAULT_MASS_TOLERANCE,
    comTolerance: DEFAULT_COM_TOLERANCE,
    inertiaTolerance: DEFAULT_INERTIA_TOLERANCE,
    principalAxesTolerance: DEFAULT_PRINCIPAL_AXES_TOLERANCE,
    jointFrameTolerance: DEFAULT_JOINT_FRAME_TOLERANCE,
    linkPositionTolerance: DEFAULT_LINK_POSITION_TOLERANCE,
    linkOrientationTolerance: DEFAULT_LINK_ORIENTATION_TOLERANCE,
    worldPositionTolerance: DEFAULT_WORLD_POSITION_TOLERANCE,
    materialColorTolerance: DEFAULT_MATERIAL_COLOR_TOLERANCE,
    maxFailureSamples: 32,
    modelFilters: [],
    help: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`Missing value for ${arg}`);
      }
      return argv[index];
    };

    switch (arg) {
      case '--browser-report':
        options.browserReportPath = path.resolve(next());
        break;
      case '--truth':
        options.truthPath = path.resolve(next());
        break;
      case '--material-truth':
        options.materialTruthPath = path.resolve(next());
        break;
      case '--output':
        options.outputPath = path.resolve(next());
        break;
      case '--model':
        options.modelFilters.push(next());
        break;
      case '--mass-tolerance':
        options.massTolerance = Number(next());
        break;
      case '--com-tolerance':
        options.comTolerance = Number(next());
        break;
      case '--inertia-tolerance':
        options.inertiaTolerance = Number(next());
        break;
      case '--principal-axes-tolerance':
        options.principalAxesTolerance = Number(next());
        break;
      case '--joint-frame-tolerance':
        options.jointFrameTolerance = Number(next());
        break;
      case '--link-position-tolerance':
        options.linkPositionTolerance = Number(next());
        break;
      case '--link-orientation-tolerance':
        options.linkOrientationTolerance = Number(next());
        break;
      case '--world-position-tolerance':
        options.worldPositionTolerance = Number(next());
        break;
      case '--material-color-tolerance':
        options.materialColorTolerance = Number(next());
        break;
      case '--max-failures':
        options.maxFailureSamples = Number.parseInt(next(), 10);
        break;
      case '--help':
      case '-h':
        options.help = true;
        break;
      default:
        throw new Error(`Unknown option: ${arg}`);
    }
  }

  if (!Number.isFinite(options.massTolerance) || options.massTolerance < 0) {
    throw new Error(`Invalid --mass-tolerance: ${options.massTolerance}`);
  }
  if (!Number.isFinite(options.comTolerance) || options.comTolerance < 0) {
    throw new Error(`Invalid --com-tolerance: ${options.comTolerance}`);
  }
  if (!Number.isFinite(options.inertiaTolerance) || options.inertiaTolerance < 0) {
    throw new Error(`Invalid --inertia-tolerance: ${options.inertiaTolerance}`);
  }
  if (!Number.isFinite(options.principalAxesTolerance) || options.principalAxesTolerance < 0) {
    throw new Error(`Invalid --principal-axes-tolerance: ${options.principalAxesTolerance}`);
  }
  if (!Number.isFinite(options.jointFrameTolerance) || options.jointFrameTolerance < 0) {
    throw new Error(`Invalid --joint-frame-tolerance: ${options.jointFrameTolerance}`);
  }
  if (!Number.isFinite(options.linkPositionTolerance) || options.linkPositionTolerance < 0) {
    throw new Error(`Invalid --link-position-tolerance: ${options.linkPositionTolerance}`);
  }
  if (!Number.isFinite(options.linkOrientationTolerance) || options.linkOrientationTolerance < 0) {
    throw new Error(`Invalid --link-orientation-tolerance: ${options.linkOrientationTolerance}`);
  }
  if (!Number.isFinite(options.worldPositionTolerance) || options.worldPositionTolerance < 0) {
    throw new Error(`Invalid --world-position-tolerance: ${options.worldPositionTolerance}`);
  }
  if (!Number.isFinite(options.materialColorTolerance) || options.materialColorTolerance < 0) {
    throw new Error(`Invalid --material-color-tolerance: ${options.materialColorTolerance}`);
  }
  if (!Number.isInteger(options.maxFailureSamples) || options.maxFailureSamples < 1) {
    throw new Error(`Invalid --max-failures: ${options.maxFailureSamples}`);
  }

  return options;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, 'utf8'));
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    printUsage();
    return;
  }

  const [browserReport, truthReport, materialTruthReport] = await Promise.all([
    readJson(options.browserReportPath),
    readJson(options.truthPath),
    options.materialTruthPath ? readJson(options.materialTruthPath) : Promise.resolve(null),
  ]);
  const comparison = compareUnitreeRosUsdaBrowserPhysics({
    browserReport,
    truthReport,
    materialTruthReport,
    massTolerance: options.massTolerance,
    comTolerance: options.comTolerance,
    inertiaTolerance: options.inertiaTolerance,
    principalAxesTolerance: options.principalAxesTolerance,
    jointFrameTolerance: options.jointFrameTolerance,
    linkPositionTolerance: options.linkPositionTolerance,
    linkOrientationTolerance: options.linkOrientationTolerance,
    worldPositionTolerance: options.worldPositionTolerance,
    materialColorTolerance: options.materialColorTolerance,
    modelFilters: options.modelFilters,
    maxFailureSamples: options.maxFailureSamples,
  });

  await fs.mkdir(path.dirname(options.outputPath), { recursive: true });
  await fs.writeFile(options.outputPath, `${JSON.stringify(comparison, null, 2)}\n`, 'utf8');

  console.log(
    JSON.stringify(
      {
        output: options.outputPath,
        pass: comparison.pass,
        summary: comparison.summary,
      },
      null,
      2,
    ),
  );

  if (!comparison.pass) {
    throw new Error(
      `Unitree ROS USDA browser physics comparison failed: ${JSON.stringify(
        comparison.failures,
        null,
        2,
      )}`,
    );
  }
}

const isCli = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isCli) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.stack || error.message : error);
    process.exitCode = 1;
  });
}

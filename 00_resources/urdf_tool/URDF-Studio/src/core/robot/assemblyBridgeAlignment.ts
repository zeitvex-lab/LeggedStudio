import * as THREE from 'three';

import type {
  AssemblyComponent,
  AssemblyState,
  AssemblyTransform,
  BridgeJoint,
  UrdfOrigin,
} from '@/types';

import { computeLinkWorldMatrices, createOriginMatrix } from './kinematics';
import { cloneAssemblyTransform } from './assemblyTransforms';
import { estimateLinkRenderableBounds } from './assemblyPlacement';
import { logRuntimeFailure } from '@/core/utils/runtimeDiagnostics';

const UNIT_SCALE = new THREE.Vector3(1, 1, 1);
const DEFAULT_BRIDGE_VISUAL_CONTACT_GAP = 0.002;
const DEFAULT_BRIDGE_VISUAL_CONTACT_DISTANCE = 0.12;
const DEFAULT_BRIDGE_VISUAL_CONTACT_DIRECTION = new THREE.Vector3(1, 0, 0);
const BRIDGE_DIRECTION_EPSILON = 1e-8;
const BRIDGE_DOMINANT_AXIS_RATIO_THRESHOLD = 1.35;

function normalizeZero(value: number): number {
  return Object.is(value, -0) || Math.abs(value) < Number.EPSILON ? 0 : value;
}

export function buildAssemblyTransformMatrix(transform?: AssemblyTransform | null): THREE.Matrix4 {
  const normalized = cloneAssemblyTransform(transform);

  return new THREE.Matrix4().compose(
    new THREE.Vector3(normalized.position.x, normalized.position.y, normalized.position.z),
    new THREE.Quaternion().setFromEuler(
      new THREE.Euler(normalized.rotation.r, normalized.rotation.p, normalized.rotation.y, 'ZYX'),
    ),
    UNIT_SCALE,
  );
}

export function decomposeAssemblyTransformMatrix(matrix: THREE.Matrix4): AssemblyTransform {
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const euler = new THREE.Euler(0, 0, 0, 'ZYX');

  matrix.decompose(position, quaternion, scale);
  euler.setFromQuaternion(quaternion, 'ZYX');

  return cloneAssemblyTransform({
    position: {
      x: normalizeZero(position.x),
      y: normalizeZero(position.y),
      z: normalizeZero(position.z),
    },
    rotation: {
      r: normalizeZero(euler.x),
      p: normalizeZero(euler.y),
      y: normalizeZero(euler.z),
    },
  });
}

export function resolveAssemblyComponentLinkId(
  component: AssemblyComponent,
  linkId: string,
): string | null {
  return component.robot.links[linkId] ? linkId : null;
}

function getMatrixPosition(matrix: THREE.Matrix4): THREE.Vector3 {
  return new THREE.Vector3().setFromMatrixPosition(matrix);
}

function normalizeDirectionOrFallback(direction: THREE.Vector3): THREE.Vector3 {
  if (direction.lengthSq() <= BRIDGE_DIRECTION_EPSILON) {
    return DEFAULT_BRIDGE_VISUAL_CONTACT_DIRECTION.clone();
  }

  return direction.normalize();
}

function snapDirectionToNearestPrincipalAxis(direction: THREE.Vector3): THREE.Vector3 {
  const normalizedDirection = normalizeDirectionOrFallback(direction);
  const components: Array<[axis: 'x' | 'y' | 'z', value: number]> = [
    ['x', normalizedDirection.x],
    ['y', normalizedDirection.y],
    ['z', normalizedDirection.z],
  ];
  components.sort((left, right) => Math.abs(right[1]) - Math.abs(left[1]));

  const [axis, value] = components[0]!;
  return new THREE.Vector3(
    axis === 'x' ? Math.sign(value || 1) : 0,
    axis === 'y' ? Math.sign(value || 1) : 0,
    axis === 'z' ? Math.sign(value || 1) : 0,
  );
}

function resolveBoundsDominantAxisDirection(
  bounds: THREE.Box3,
  referenceDirection: THREE.Vector3,
): THREE.Vector3 | null {
  const size = bounds.getSize(new THREE.Vector3());
  const components: Array<[axis: 'x' | 'y' | 'z', size: number]> = [
    ['x', size.x],
    ['y', size.y],
    ['z', size.z],
  ];
  components.sort((left, right) => right[1] - left[1]);

  const [dominantAxis, dominantSize] = components[0]!;
  const secondarySize = components[1]?.[1] ?? 0;
  if (
    dominantSize <= BRIDGE_DIRECTION_EPSILON ||
    dominantSize < secondarySize * BRIDGE_DOMINANT_AXIS_RATIO_THRESHOLD
  ) {
    return null;
  }

  const dominantReferenceComponent =
    dominantAxis === 'x'
      ? referenceDirection.x
      : dominantAxis === 'y'
        ? referenceDirection.y
        : referenceDirection.z;
  const dominantSign = Math.sign(dominantReferenceComponent || 1);
  return new THREE.Vector3(
    dominantAxis === 'x' ? dominantSign : 0,
    dominantAxis === 'y' ? dominantSign : 0,
    dominantAxis === 'z' ? dominantSign : 0,
  );
}

function getParentLinkLocalContactDirection({
  parentRootMatrix,
  parentLinkLocalMatrix,
  childRootMatrix,
  childLinkLocalMatrix,
}: {
  parentRootMatrix: THREE.Matrix4;
  parentLinkLocalMatrix: THREE.Matrix4;
  childRootMatrix: THREE.Matrix4;
  childLinkLocalMatrix: THREE.Matrix4;
}): THREE.Vector3 {
  const parentLinkWorldMatrix = parentRootMatrix.clone().multiply(parentLinkLocalMatrix);
  const childLinkWorldMatrix = childRootMatrix.clone().multiply(childLinkLocalMatrix);
  const directionWorld = getMatrixPosition(childLinkWorldMatrix).sub(
    getMatrixPosition(parentLinkWorldMatrix),
  );

  if (directionWorld.lengthSq() <= BRIDGE_DIRECTION_EPSILON) {
    directionWorld.copy(
      DEFAULT_BRIDGE_VISUAL_CONTACT_DIRECTION.clone().transformDirection(parentLinkWorldMatrix),
    );
  }

  const parentWorldQuaternion = new THREE.Quaternion();
  parentLinkWorldMatrix.decompose(new THREE.Vector3(), parentWorldQuaternion, new THREE.Vector3());

  const directionLocal = normalizeDirectionOrFallback(directionWorld).applyQuaternion(
    parentWorldQuaternion.clone().invert(),
  );

  return normalizeDirectionOrFallback(directionLocal);
}

function getBoxCorners(bounds: THREE.Box3): THREE.Vector3[] {
  return [
    new THREE.Vector3(bounds.min.x, bounds.min.y, bounds.min.z),
    new THREE.Vector3(bounds.min.x, bounds.min.y, bounds.max.z),
    new THREE.Vector3(bounds.min.x, bounds.max.y, bounds.min.z),
    new THREE.Vector3(bounds.min.x, bounds.max.y, bounds.max.z),
    new THREE.Vector3(bounds.max.x, bounds.min.y, bounds.min.z),
    new THREE.Vector3(bounds.max.x, bounds.min.y, bounds.max.z),
    new THREE.Vector3(bounds.max.x, bounds.max.y, bounds.min.z),
    new THREE.Vector3(bounds.max.x, bounds.max.y, bounds.max.z),
  ];
}

function projectBoundsOntoDirection(
  bounds: THREE.Box3,
  direction: THREE.Vector3,
  transform?: THREE.Matrix4,
): { min: number; max: number } {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;

  getBoxCorners(bounds).forEach((corner) => {
    const projectedCorner = transform ? corner.applyMatrix4(transform) : corner;
    const projection = projectedCorner.dot(direction);
    min = Math.min(min, projection);
    max = Math.max(max, projection);
  });

  return { min, max };
}

export function resolveSuggestedBridgeOriginForVisualContact({
  assemblyState,
  parentComponentId,
  parentLinkId,
  childComponentId,
  childLinkId,
  origin,
  gap = DEFAULT_BRIDGE_VISUAL_CONTACT_GAP,
}: {
  assemblyState: AssemblyState;
  parentComponentId: string;
  parentLinkId: string;
  childComponentId: string;
  childLinkId: string;
  origin?: UrdfOrigin | null;
  gap?: number;
}): AssemblyTransform['position'] | null {
  const parentComponent = assemblyState.components[parentComponentId];
  const childComponent = assemblyState.components[childComponentId];

  if (!parentComponent || !childComponent || parentComponentId === childComponentId) {
    return null;
  }

  const resolvedParentLinkId = resolveAssemblyComponentLinkId(parentComponent, parentLinkId);
  const resolvedChildLinkId = resolveAssemblyComponentLinkId(childComponent, childLinkId);
  if (!resolvedParentLinkId || !resolvedChildLinkId) {
    return null;
  }

  const parentLinkLocalMatrices = computeLinkWorldMatrices(parentComponent.robot);
  const childLinkLocalMatrices = computeLinkWorldMatrices(childComponent.robot);
  const parentLinkLocalMatrix = parentLinkLocalMatrices[resolvedParentLinkId];
  const childLinkLocalMatrix = childLinkLocalMatrices[resolvedChildLinkId];
  const parentLink = parentComponent.robot.links[resolvedParentLinkId];
  const childLink = childComponent.robot.links[resolvedChildLinkId];
  if (!parentLinkLocalMatrix || !childLinkLocalMatrix || !parentLink || !childLink) {
    return null;
  }

  const parentRootMatrix = buildAssemblyTransformMatrix(parentComponent.transform);
  const childRootMatrix = buildAssemblyTransformMatrix(childComponent.transform);
  const directionLocal = getParentLinkLocalContactDirection({
    parentRootMatrix,
    parentLinkLocalMatrix,
    childRootMatrix,
    childLinkLocalMatrix,
  });

  const parentBounds = estimateLinkRenderableBounds(parentLink);
  const childBounds = estimateLinkRenderableBounds(childLink);
  const snappedDirectionLocal =
    resolveBoundsDominantAxisDirection(
      parentBounds ?? childBounds ?? new THREE.Box3(),
      directionLocal,
    ) ?? snapDirectionToNearestPrincipalAxis(directionLocal);
  if (!parentBounds || !childBounds) {
    logRuntimeFailure(
      'AssemblyBridgeAlignment',
      new Error(
        `Falling back to default bridge contact distance because renderable bounds are missing. parentComponentId=${parentComponentId}; parentLinkId=${resolvedParentLinkId}; childComponentId=${childComponentId}; childLinkId=${resolvedChildLinkId}`,
      ),
    );
    const fallbackOffset = snappedDirectionLocal.multiplyScalar(
      DEFAULT_BRIDGE_VISUAL_CONTACT_DISTANCE,
    );
    return {
      x: normalizeZero(fallbackOffset.x),
      y: normalizeZero(fallbackOffset.y),
      z: normalizeZero(fallbackOffset.z),
    };
  }

  const childRotationOnlyMatrix = createOriginMatrix({
    xyz: { x: 0, y: 0, z: 0 },
    rpy: origin?.rpy,
  });
  const parentProjection = projectBoundsOntoDirection(parentBounds, snappedDirectionLocal);
  const childProjection = projectBoundsOntoDirection(
    childBounds,
    snappedDirectionLocal,
    childRotationOnlyMatrix,
  );
  const offsetDistance = parentProjection.max - childProjection.min + gap;
  const suggestedOffset = snappedDirectionLocal.multiplyScalar(offsetDistance);

  return {
    x: normalizeZero(suggestedOffset.x),
    y: normalizeZero(suggestedOffset.y),
    z: normalizeZero(suggestedOffset.z),
  };
}

export function resolveAlignedAssemblyComponentTransformForBridge(
  assemblyState: AssemblyState,
  bridge: BridgeJoint,
): AssemblyTransform | null {
  const parentComponent = assemblyState.components[bridge.parentComponentId];
  const childComponent = assemblyState.components[bridge.childComponentId];

  if (!parentComponent || !childComponent) {
    return null;
  }

  const resolvedParentLinkId = resolveAssemblyComponentLinkId(parentComponent, bridge.parentLinkId);
  const resolvedChildLinkId = resolveAssemblyComponentLinkId(childComponent, bridge.childLinkId);
  if (!resolvedParentLinkId || !resolvedChildLinkId) {
    return null;
  }

  const parentLinkWorldMatrices = computeLinkWorldMatrices(parentComponent.robot);
  const childLinkWorldMatrices = computeLinkWorldMatrices(childComponent.robot);
  const parentLinkLocalMatrix = parentLinkWorldMatrices[resolvedParentLinkId];
  const childLinkLocalMatrix = childLinkWorldMatrices[resolvedChildLinkId];
  if (!parentLinkLocalMatrix || !childLinkLocalMatrix) {
    return null;
  }

  const parentRootMatrix = buildAssemblyTransformMatrix(parentComponent.transform);
  const parentLinkWorldMatrix = parentRootMatrix.clone().multiply(parentLinkLocalMatrix);
  const childRootWorldMatrix = parentLinkWorldMatrix
    .clone()
    .multiply(createOriginMatrix(bridge.joint.origin))
    .multiply(childLinkLocalMatrix.clone().invert());

  return decomposeAssemblyTransformMatrix(childRootWorldMatrix);
}

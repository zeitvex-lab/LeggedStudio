import * as THREE from 'three';

import type { AssemblyTransform } from '@/types';

import { decomposeAssemblyTransformMatrix } from './assemblyBridgeAlignment';

/**
 * Fusion 360 style "Joint Alignment" adjustment, expressed in the picked snap
 * (joint origin) frame: rotate about the joint axis (snap +Z), translate along
 * the snap axes, and optionally flip 180 deg about snap +X.
 */
export interface JointAlignmentDelta {
  angleRad: number;
  offset: { x: number; y: number; z: number };
  flip: boolean;
}

export const IDENTITY_JOINT_ALIGNMENT: JointAlignmentDelta = {
  angleRad: 0,
  offset: { x: 0, y: 0, z: 0 },
  flip: false,
};

export interface BridgeOriginFromSnapParams {
  /** World pose of the parent snap (joint origin) frame. */
  parentSnapWorld: THREE.Matrix4;
  /** World pose of the child snap frame, at the child's CURRENT transform. */
  childSnapWorld: THREE.Matrix4;
  /** World pose of the parent link frame. */
  parentLinkWorld: THREE.Matrix4;
  /** World pose of the child link frame, at the child's CURRENT transform. */
  childLinkWorld: THREE.Matrix4;
  /** Joint alignment adjustment in the snap frame. Defaults to identity. */
  alignment?: JointAlignmentDelta;
}

export interface BridgeOriginResult {
  matrix: THREE.Matrix4;
  transform: AssemblyTransform;
}

/**
 * Build the alignment delta matrix in the snap frame:
 *   T(offset) x Rz(angle) x Rx(flip ? pi : 0)
 */
export function buildJointAlignmentDeltaMatrix(alignment: JointAlignmentDelta): THREE.Matrix4 {
  const translation = new THREE.Matrix4().makeTranslation(
    alignment.offset.x,
    alignment.offset.y,
    alignment.offset.z,
  );
  const rotationZ = new THREE.Matrix4().makeRotationZ(alignment.angleRad);
  const flip = new THREE.Matrix4().makeRotationX(alignment.flip ? Math.PI : 0);

  return translation.multiply(rotationZ).multiply(flip);
}

/**
 * Compute the bridge joint origin (child link pose expressed in the parent link
 * frame) such that the child snap frame coincides with the parent snap frame
 * (modulo the alignment delta) after the child component is re-aligned.
 *
 * Derivation (all matrices in the same world space; origin is the parent-link ->
 * child-link relative pose, so it is invariant to any shared rigid transform):
 *   origin = parentLinkWorld^-1 . parentSnapWorld . alignment . childSnapWorld^-1 . childLinkWorld
 *
 * This is the exact inverse of `resolveAlignedAssemblyComponentTransformForBridge`,
 * whose contract is `createOriginMatrix(origin) = parentLinkWorld^-1 . childLinkWorld`.
 */
export function computeBridgeOriginFromSnapFrames(
  params: BridgeOriginFromSnapParams,
): BridgeOriginResult {
  const alignment = params.alignment ?? IDENTITY_JOINT_ALIGNMENT;
  const alignmentMatrix = buildJointAlignmentDeltaMatrix(alignment);

  const matrix = new THREE.Matrix4()
    .copy(params.parentLinkWorld)
    .invert()
    .multiply(params.parentSnapWorld)
    .multiply(alignmentMatrix)
    .multiply(new THREE.Matrix4().copy(params.childSnapWorld).invert())
    .multiply(params.childLinkWorld);

  return { matrix, transform: decomposeAssemblyTransformMatrix(matrix) };
}

export interface PointCoincidentOriginParams {
  parentSnapPointWorld: THREE.Vector3;
  childSnapPointWorld: THREE.Vector3;
  parentLinkWorld: THREE.Matrix4;
  childLinkWorld: THREE.Matrix4;
}

/**
 * "Point coincident" variant: translate the child so the two snap points meet
 * while preserving the child's current orientation (no normal alignment).
 *   origin = parentLinkWorld^-1 . T(parentPoint - childPoint) . childLinkWorld
 */
export function computePointCoincidentOrigin(
  params: PointCoincidentOriginParams,
): BridgeOriginResult {
  const delta = params.parentSnapPointWorld.clone().sub(params.childSnapPointWorld);
  const childLinkWorldNew = new THREE.Matrix4()
    .makeTranslation(delta.x, delta.y, delta.z)
    .multiply(params.childLinkWorld);

  const matrix = new THREE.Matrix4()
    .copy(params.parentLinkWorld)
    .invert()
    .multiply(childLinkWorldNew);

  return { matrix, transform: decomposeAssemblyTransformMatrix(matrix) };
}

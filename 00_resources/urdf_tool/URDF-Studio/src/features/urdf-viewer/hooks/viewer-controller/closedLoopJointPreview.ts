import { getJointType } from '@/shared/utils/jointTypes';
import { resolveViewerJointKey } from '@/shared/utils/jointPanelState';
import { unwrapContinuousJointAngle } from '@/shared/utils/continuousJointAngle';
import { getJointActualAngleFromMotionAngle } from '@/core/robot';
import { JointType, type JointQuaternion, type RobotState } from '@/types';
import type { ViewerJointMotionStateValue } from '../../types';

export type ViewerJointInteractionSource = 'r3f' | 'runtime';
export type ViewerJointInteractionAngleSpace = 'actual' | 'runtime';

export interface ViewerJointInteractionEvent {
  source: ViewerJointInteractionSource;
  jointName: string;
  angle: number;
  angleSpace: ViewerJointInteractionAngleSpace;
}

export const JOINT_SYNC_EPSILON = 1e-6;
export const CLOSED_LOOP_PREVIEW_MAX_IN_FLIGHT = 2;

export function isSameJointAngle(left: number | undefined, right: number | undefined) {
  if (typeof left !== 'number' || typeof right !== 'number') {
    return left === right;
  }

  return Math.abs(left - right) <= JOINT_SYNC_EPSILON;
}

export function isSameJointQuaternion(
  left: ViewerJointMotionStateValue['quaternion'] | null | undefined,
  right: ViewerJointMotionStateValue['quaternion'] | null | undefined,
) {
  if (!left || !right) {
    return left === right;
  }

  return (
    isSameJointAngle(left.x, right.x) &&
    isSameJointAngle(left.y, right.y) &&
    isSameJointAngle(left.z, right.z) &&
    isSameJointAngle(left.w, right.w)
  );
}

export function isSameJointMotion(
  left: ViewerJointMotionStateValue | undefined,
  right: ViewerJointMotionStateValue | undefined,
) {
  if (!left || !right) {
    return left === right;
  }

  return (
    isSameJointAngle(left.angle, right.angle) &&
    isSameJointQuaternion(left.quaternion, right.quaternion)
  );
}

type RuntimePoseJointQuaternionLike =
  | ViewerJointMotionStateValue['quaternion']
  | { x?: unknown; y?: unknown; z?: unknown; w?: unknown };

export type RuntimePoseJointLike = {
  name?: string;
  angle?: number;
  jointValue?: number;
  referencePosition?: number;
  jointQuaternion?: RuntimePoseJointQuaternionLike;
  quaternion?: RuntimePoseJointQuaternionLike;
};

export interface ClosedLoopPreviewCommitState {
  baseRobot: Pick<RobotState, 'links' | 'joints' | 'rootLinkId' | 'closedLoopConstraints'> | null;
  selectedJointId: string;
  resolvedAngle: number;
  jointAngles: Record<string, number>;
  jointQuaternions: Record<string, JointQuaternion>;
}

export function compactJointQuaternions(
  jointQuaternions: Record<string, ViewerJointMotionStateValue['quaternion']>,
): Record<string, JointQuaternion> {
  return Object.fromEntries(
    Object.entries(jointQuaternions).filter(
      (entry): entry is [string, JointQuaternion] => Boolean(entry[1]),
    ),
  );
}

export function resolveClosedLoopPreviewAngles(
  selectedJointId: string,
  requestedAngle: number,
  solution: {
    angles: Record<string, number>;
    appliedAngle: number | null;
    constrained: boolean;
  },
): {
  angles: Record<string, number>;
  activeAngle: number;
  preserveActiveJointRuntime: boolean;
} {
  const activeAngle =
    typeof solution.appliedAngle === 'number' && Number.isFinite(solution.appliedAngle)
      ? solution.appliedAngle
      : typeof solution.angles[selectedJointId] === 'number'
        ? solution.angles[selectedJointId]
        : requestedAngle;
  const angles = { ...solution.angles };
  angles[selectedJointId] = activeAngle;

  return {
    angles,
    activeAngle,
    preserveActiveJointRuntime:
      !solution.constrained && isSameJointAngle(activeAngle, requestedAngle),
  };
}

function toFiniteNumber(value: unknown): number | null {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

// Runtime joints may expose live THREE.Quaternion instances; keep solver state plain-data and cloneable.
function toJointQuaternionValue(
  quaternion: RuntimePoseJointQuaternionLike | null | undefined,
): JointQuaternion | null {
  if (!quaternion) {
    return null;
  }

  const x = toFiniteNumber(quaternion.x);
  const y = toFiniteNumber(quaternion.y);
  const z = toFiniteNumber(quaternion.z);
  const w = toFiniteNumber(quaternion.w);
  if (x === null || y === null || z === null || w === null) {
    return null;
  }

  return { x, y, z, w };
}

function getRuntimeJointMotionQuaternion(
  joint: RuntimePoseJointLike | null | undefined,
): JointQuaternion | null {
  return toJointQuaternionValue(joint?.jointQuaternion ?? joint?.quaternion);
}

export function getRuntimeJointCurrentMotionQuaternion(joint: unknown): JointQuaternion | null {
  const runtimeJoint = joint as
    | {
        jointQuaternion?: RuntimePoseJointQuaternionLike;
        quaternion?: RuntimePoseJointQuaternionLike;
      }
    | null
    | undefined;
  return toJointQuaternionValue(runtimeJoint?.jointQuaternion ?? runtimeJoint?.quaternion);
}

function toClosedLoopPreviewJoint(
  joint: RobotState['joints'][string],
): RobotState['joints'][string] {
  const normalizedQuaternion = toJointQuaternionValue(joint.quaternion);

  return {
    id: joint.id,
    name: joint.name,
    type: joint.type,
    parentLinkId: joint.parentLinkId,
    childLinkId: joint.childLinkId,
    origin: {
      xyz: { ...joint.origin.xyz },
      rpy: { ...joint.origin.rpy },
    },
    dynamics: { ...joint.dynamics },
    hardware: { ...joint.hardware },
    ...(joint.axis ? { axis: { ...joint.axis } } : {}),
    ...(joint.limit ? { limit: { ...joint.limit } } : {}),
    ...(joint.mimic ? { mimic: { ...joint.mimic } } : {}),
    ...(joint.calibration ? { calibration: { ...joint.calibration } } : {}),
    ...(joint.safetyController ? { safetyController: { ...joint.safetyController } } : {}),
    ...(typeof joint.referencePosition === 'number'
      ? { referencePosition: joint.referencePosition }
      : {}),
    ...(typeof joint.angle === 'number' ? { angle: joint.angle } : {}),
    ...(normalizedQuaternion ? { quaternion: normalizedQuaternion } : {}),
  };
}

export function mergeClosedLoopRobotStateWithRuntimeJointPose(
  closedLoopRobotState: Pick<
    RobotState,
    'links' | 'joints' | 'rootLinkId' | 'closedLoopConstraints'
  > | null,
  runtimeJoints: Record<string, RuntimePoseJointLike> | null | undefined,
): Pick<RobotState, 'links' | 'joints' | 'rootLinkId' | 'closedLoopConstraints'> | null {
  if (!closedLoopRobotState) {
    return null;
  }

  const nextClosedLoopRobotState: Pick<
    RobotState,
    'links' | 'joints' | 'rootLinkId' | 'closedLoopConstraints'
  > = {
    ...closedLoopRobotState,
    joints: Object.fromEntries(
      Object.entries(closedLoopRobotState.joints).map(([jointId, joint]) => [
        jointId,
        toClosedLoopPreviewJoint(joint),
      ]),
    ),
  };

  if (!runtimeJoints) {
    return nextClosedLoopRobotState;
  }

  Object.entries(runtimeJoints).forEach(([runtimeJointId, runtimeJoint]) => {
    const resolvedJointKey =
      resolveViewerJointKey(
        nextClosedLoopRobotState.joints,
        runtimeJoint?.name || runtimeJointId,
      ) ?? (runtimeJointId in nextClosedLoopRobotState.joints ? runtimeJointId : null);
    if (!resolvedJointKey) {
      return;
    }

    const baseJoint = nextClosedLoopRobotState.joints[resolvedJointKey];
    if (!baseJoint) {
      return;
    }

    const nextMotionAngle = toFiniteNumber(runtimeJoint?.angle ?? runtimeJoint?.jointValue);
    const nextAngle =
      nextMotionAngle !== null
        ? resolveRuntimeReportedJointAngle(baseJoint, runtimeJoint, nextMotionAngle)
        : null;
    const nextQuaternion = getRuntimeJointMotionQuaternion(runtimeJoint);
    const shouldUpdateAngle = nextAngle !== null && !isSameJointAngle(baseJoint.angle, nextAngle);
    const shouldUpdateQuaternion =
      Boolean(nextQuaternion) && !isSameJointQuaternion(baseJoint.quaternion, nextQuaternion);
    if (!shouldUpdateAngle && !shouldUpdateQuaternion) {
      return;
    }

    nextClosedLoopRobotState.joints[resolvedJointKey] = {
      ...baseJoint,
      ...(shouldUpdateAngle && nextAngle !== null ? { angle: nextAngle } : {}),
      ...(shouldUpdateQuaternion && nextQuaternion ? { quaternion: nextQuaternion } : {}),
    };
  });

  return nextClosedLoopRobotState;
}

export function resolveRuntimeReportedJointAngle(
  stateJoint: RobotState['joints'][string] | undefined,
  runtimeJoint: unknown,
  runtimeMotionAngle: number,
): number {
  const actualAngle = stateJoint
    ? getJointActualAngleFromMotionAngle(stateJoint, runtimeMotionAngle)
    : runtimeMotionAngle;
  const jointType = stateJoint?.type ?? getJointType(runtimeJoint);

  if (jointType !== JointType.CONTINUOUS) {
    return actualAngle;
  }

  const referenceAngle = Number(stateJoint?.angle ?? actualAngle);

  if (!Number.isFinite(referenceAngle)) {
    return actualAngle;
  }

  return unwrapContinuousJointAngle(actualAngle, referenceAngle);
}

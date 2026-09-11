import type { JointQuaternion, RobotState, UrdfJoint } from '@/types';

export interface JointInteractionPreview {
  source: 'viewer';
  dragSessionId: string;
  activeJointId: string | null;
  jointAngles: Record<string, number>;
  jointQuaternions: Record<string, JointQuaternion>;
  jointOrigins: Record<string, UrdfJoint['origin']>;
}

const PREVIEW_EPSILON = 1e-6;

function isSameNumber(left: number | undefined, right: number | undefined): boolean {
  if (typeof left !== 'number' || typeof right !== 'number') {
    return left === right;
  }

  return Math.abs(left - right) <= PREVIEW_EPSILON;
}

function isSameQuaternion(left: JointQuaternion | undefined, right: JointQuaternion | undefined) {
  if (!left || !right) {
    return left === right;
  }

  return (
    isSameNumber(left.x, right.x) &&
    isSameNumber(left.y, right.y) &&
    isSameNumber(left.z, right.z) &&
    isSameNumber(left.w, right.w)
  );
}

function isSameOrigin(
  left: UrdfJoint['origin'] | undefined,
  right: UrdfJoint['origin'] | undefined,
): boolean {
  if (!left || !right) {
    return left === right;
  }

  return (
    isSameNumber(left.xyz.x, right.xyz.x) &&
    isSameNumber(left.xyz.y, right.xyz.y) &&
    isSameNumber(left.xyz.z, right.xyz.z) &&
    isSameNumber(left.rpy.r, right.rpy.r) &&
    isSameNumber(left.rpy.p, right.rpy.p) &&
    isSameNumber(left.rpy.y, right.rpy.y)
  );
}

function cloneOrigin(origin: UrdfJoint['origin']): UrdfJoint['origin'] {
  return {
    xyz: {
      x: origin.xyz.x ?? 0,
      y: origin.xyz.y ?? 0,
      z: origin.xyz.z ?? 0,
    },
    rpy: {
      r: origin.rpy.r ?? 0,
      p: origin.rpy.p ?? 0,
      y: origin.rpy.y ?? 0,
    },
  };
}

function cloneQuaternion(quaternion: JointQuaternion): JointQuaternion {
  return {
    x: quaternion.x,
    y: quaternion.y,
    z: quaternion.z,
    w: quaternion.w,
  };
}

export function applyJointInteractionPreview(
  robot: RobotState,
  preview: JointInteractionPreview | null,
): RobotState {
  if (!preview) {
    return robot;
  }

  const affectedJointIds = new Set([
    ...Object.keys(preview.jointAngles),
    ...Object.keys(preview.jointQuaternions),
    ...Object.keys(preview.jointOrigins),
  ]);

  if (affectedJointIds.size === 0) {
    return robot;
  }

  const nextJoints: Record<string, UrdfJoint> = {};
  let hasChanges = false;

  affectedJointIds.forEach((jointId) => {
    const joint = robot.joints[jointId];
    if (!joint) {
      return;
    }

    let nextJoint = joint;
    const nextAngle = preview.jointAngles[jointId];
    if (typeof nextAngle === 'number' && !isSameNumber(joint.angle, nextAngle)) {
      nextJoint = nextJoint === joint ? { ...joint } : nextJoint;
      nextJoint.angle = nextAngle;
    }

    const nextQuaternion = preview.jointQuaternions[jointId];
    if (nextQuaternion && !isSameQuaternion(joint.quaternion, nextQuaternion)) {
      nextJoint = nextJoint === joint ? { ...joint } : nextJoint;
      nextJoint.quaternion = cloneQuaternion(nextQuaternion);
    }

    const nextOrigin = preview.jointOrigins[jointId];
    if (nextOrigin && !isSameOrigin(joint.origin, nextOrigin)) {
      nextJoint = nextJoint === joint ? { ...joint } : nextJoint;
      nextJoint.origin = cloneOrigin(nextOrigin);
    }

    if (nextJoint !== joint) {
      nextJoints[jointId] = nextJoint;
      hasChanges = true;
    }
  });

  if (!hasChanges) {
    return robot;
  }

  return {
    ...robot,
    joints: {
      ...robot.joints,
      ...nextJoints,
    },
  };
}

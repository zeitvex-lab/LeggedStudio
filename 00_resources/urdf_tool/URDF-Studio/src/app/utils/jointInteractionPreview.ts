import type { JointQuaternion, RobotState, UrdfJoint } from '@/types';

export interface JointInteractionPreviewLike {
  jointAngles: Record<string, number>;
  jointQuaternions: Record<string, JointQuaternion>;
  jointOrigins: Record<string, UrdfJoint['origin']>;
}

export function hasJointInteractionPreviewLike(
  preview: JointInteractionPreviewLike | null | undefined,
): preview is JointInteractionPreviewLike {
  if (!preview) {
    return false;
  }

  return (
    Object.keys(preview.jointAngles).length > 0 ||
    Object.keys(preview.jointQuaternions).length > 0 ||
    Object.keys(preview.jointOrigins).length > 0
  );
}

export function applyJointInteractionPreviewToRobot(
  robot: RobotState,
  preview: JointInteractionPreviewLike | null | undefined,
): RobotState {
  if (!hasJointInteractionPreviewLike(preview)) {
    return robot;
  }

  let nextJoints: RobotState['joints'] | null = null;

  const ensureJointMap = () => {
    if (!nextJoints) {
      nextJoints = { ...robot.joints };
    }
    return nextJoints;
  };

  Object.keys({
    ...preview.jointAngles,
    ...preview.jointQuaternions,
    ...preview.jointOrigins,
  }).forEach((jointId) => {
    const currentJoint = robot.joints[jointId];
    if (!currentJoint) {
      return;
    }

    const nextAngle = preview.jointAngles[jointId];
    const nextQuaternion = preview.jointQuaternions[jointId];
    const nextOrigin = preview.jointOrigins[jointId];

    const angleChanged = typeof nextAngle === 'number' && nextAngle !== currentJoint.angle;
    const quaternionChanged = Boolean(nextQuaternion) && nextQuaternion !== currentJoint.quaternion;
    const originChanged = Boolean(nextOrigin) && nextOrigin !== currentJoint.origin;

    if (!angleChanged && !quaternionChanged && !originChanged) {
      return;
    }

    ensureJointMap()[jointId] = {
      ...currentJoint,
      angle: angleChanged ? nextAngle : currentJoint.angle,
      quaternion: quaternionChanged ? nextQuaternion : currentJoint.quaternion,
      origin: originChanged ? nextOrigin : currentJoint.origin,
    };
  });

  return nextJoints ? { ...robot, joints: nextJoints } : robot;
}

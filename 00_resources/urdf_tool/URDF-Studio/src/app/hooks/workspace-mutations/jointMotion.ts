import type { ViewerJointChangeContext } from '@/features/editor';
import type { JointQuaternion, UrdfJoint } from '@/types';

export interface ResolvedJointMotion {
  angles: Record<string, number>;
  quaternions: Record<string, JointQuaternion>;
}

/** Resolve viewer motion only inside an already-selected component. */
export function resolveViewerJointChangeContext(
  joints: Record<string, UrdfJoint>,
  jointId: string,
  angle: number,
  context?: ViewerJointChangeContext,
): ResolvedJointMotion | null {
  if (!context || !joints[jointId]) {
    return null;
  }

  const angles: Record<string, number> = {};
  const quaternions: Record<string, JointQuaternion> = {};

  Object.entries(context.jointAngles ?? {}).forEach(([contextJointId, nextAngle]) => {
    if (joints[contextJointId] && Number.isFinite(nextAngle)) {
      angles[contextJointId] = nextAngle;
    }
  });

  Object.entries(context.jointQuaternions ?? {}).forEach(
    ([contextJointId, quaternion]) => {
      if (joints[contextJointId]) {
        quaternions[contextJointId] = quaternion;
      }
    },
  );

  if (
    Number.isFinite(angle)
    && (Object.keys(angles).length > 0 || Object.keys(quaternions).length > 0)
    && !Object.hasOwn(angles, jointId)
  ) {
    angles[jointId] = angle;
  }

  return Object.keys(angles).length === 0 && Object.keys(quaternions).length === 0
    ? null
    : { angles, quaternions };
}

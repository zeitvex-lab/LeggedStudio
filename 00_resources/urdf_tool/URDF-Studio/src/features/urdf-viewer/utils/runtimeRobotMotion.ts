import type { RuntimeRobotObject } from '@/shared/components/3d/runtimeRobotTypes';
import type { JointQuaternion } from '@/types';

export interface RuntimeViewerJoint {
  name?: string;
  type: string;
  jointType?: string;
  angle?: number;
  jointValue?: number;
  ignoreLimits?: boolean;
  referencePosition?: number;
  jointQuaternion?: JointQuaternion | { x?: unknown; y?: unknown; z?: unknown; w?: unknown };
  quaternion?: JointQuaternion | { x?: unknown; y?: unknown; z?: unknown; w?: unknown };
  setJointValue?: (value: number) => void;
  setJointQuaternion?: (quaternion: JointQuaternion) => void;
}

export type RuntimeViewerRobot = Omit<RuntimeRobotObject, 'joints'> & {
  joints?: Record<string, RuntimeViewerJoint>;
};

export function hasRuntimeJointQuaternionSetter(
  joint: RuntimeViewerJoint | null | undefined,
): joint is RuntimeViewerJoint & { setJointQuaternion: (quaternion: JointQuaternion) => void } {
  return typeof joint?.setJointQuaternion === 'function';
}

export interface JointQuaternionLike {
  x: number;
  y: number;
  z: number;
  w: number;
}

export interface RememberedJointMotion {
  angle?: number;
  quaternion?: JointQuaternionLike;
}

export type FileJointMotionMemory = Record<string, Record<string, RememberedJointMotion>>;

interface JointWithMotionLike {
  id?: string;
  name?: string;
  angle?: number;
  quaternion?: JointQuaternionLike;
}

interface RobotWithJointsLike<TJoint extends JointWithMotionLike = JointWithMotionLike> {
  joints: Record<string, TJoint>;
}

export function captureRememberedFileJointMotion<TJoint extends JointWithMotionLike>(
  _filePath: string | null | undefined,
  _robot: RobotWithJointsLike<TJoint> | null | undefined,
  existingMemory: FileJointMotionMemory = {},
): FileJointMotionMemory {
  // Transient joint pose is intentionally not persisted across file switches or
  // preview sessions. Real edits, such as collision/body changes, continue to
  // persist through the normal source/store sync pipeline instead.
  return existingMemory;
}

export function applyRememberedFileJointMotion<TJoint extends JointWithMotionLike, TRobot extends RobotWithJointsLike<TJoint>>(
  _filePath: string | null | undefined,
  robot: TRobot,
  _memory: FileJointMotionMemory,
): TRobot {
  return robot;
}

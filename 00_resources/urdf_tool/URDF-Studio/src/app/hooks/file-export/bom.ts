import type { RobotState } from '@/types';

export interface BomLabels {
  armature: string;
  direction: string;
  jointName: string;
  lower: string;
  motorId: string;
  motorType: string;
  type: string;
  upper: string;
}

export function generateRobotBomCsv(robot: RobotState, labels: BomLabels): string {
  const headers = [
    labels.jointName,
    labels.type,
    labels.motorType,
    labels.motorId,
    labels.direction,
    labels.armature,
    labels.lower,
    labels.upper,
  ];

  const rows = Object.values(robot.joints)
    .map((joint) => {
      if (joint.type === 'fixed') {
        return null;
      }
      if (!joint.hardware?.motorType || joint.hardware.motorType === 'None') {
        return null;
      }

      return [
        joint.name,
        joint.type,
        joint.hardware.motorType,
        joint.hardware.motorId || '',
        joint.hardware.motorDirection || 1,
        joint.hardware.armature || 0,
        joint.limit?.lower ?? '',
        joint.limit?.upper ?? '',
      ].join(',');
    })
    .filter((row) => row !== null);

  return [headers.join(','), ...rows].join('\n');
}

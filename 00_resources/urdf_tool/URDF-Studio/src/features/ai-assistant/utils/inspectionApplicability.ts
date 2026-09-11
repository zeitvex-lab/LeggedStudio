import type { RobotState } from '@/types'
import {
  inferInspectionRobotTypes,
  type InspectionRobotMorphology,
} from './inspectionProfileRecommendation'

export type InspectionApplicabilityStatus =
  | 'applicable'
  | 'not_applicable'
  | 'insufficient_evidence'

export interface InspectionApplicabilityOverride {
  sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
  robotTypes?: InspectionRobotMorphology[]
}

const PROFILE_ROBOT_TYPES: Record<string, InspectionRobotMorphology> = {
  'morph.humanoid': 'humanoid',
  'morph.biped': 'biped',
  'morph.quadruped': 'quadruped',
  'morph.manipulator': 'manipulator',
  'morph.mobile_base': 'mobile_base',
  'morph.gripper': 'gripper',
  'morph.dexterous_hand': 'dexterous_hand',
  'morph.parallel_mechanism': 'parallel_mechanism',
}

const PROFILE_SOURCE_FORMATS: Record<string, string> = {
  'format.urdf': 'urdf',
  'format.mjcf': 'mjcf',
  'format.xacro': 'xacro',
  'format.sdf': 'sdf',
  'format.usd': 'usd',
}

export function isInspectionItemApplicable(
  robot: RobotState,
  profileId: string,
  itemId?: string,
  override?: InspectionApplicabilityOverride,
): InspectionApplicabilityStatus {
  void itemId

  const requiredRobotType = PROFILE_ROBOT_TYPES[profileId]
  const robotTypes = override?.robotTypes ?? inferInspectionRobotTypes(robot)
  if (requiredRobotType && !robotTypes.includes(requiredRobotType)) {
    return 'not_applicable'
  }

  const requiredSourceFormat = PROFILE_SOURCE_FORMATS[profileId]
  if (requiredSourceFormat) {
    const sourceFormat = override?.sourceFormat ?? robot.inspectionContext?.sourceFormat
    if (!sourceFormat && requiredSourceFormat !== 'urdf') {
      return 'insufficient_evidence'
    }
    if ((sourceFormat ?? 'urdf') !== requiredSourceFormat) {
      return 'not_applicable'
    }
  }

  return 'applicable'
}

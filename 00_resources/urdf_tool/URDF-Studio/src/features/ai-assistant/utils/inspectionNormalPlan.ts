import type { RobotState } from '@/types'
import { INSPECTION_PROFILE_DEFINITIONS, getInspectionProfileDefinition } from '../config/inspectionProfiles'
import { isInspectionItemApplicable, type InspectionApplicabilityStatus } from './inspectionApplicability'
import {
  buildInspectionProfileRecommendation,
  type InspectionProfileRecommendation,
  type InspectionRobotType,
  type InspectionTargetPlatform,
  type InspectionWorkflowRecommendationContext,
} from './inspectionProfileRecommendation'
import type { SelectedInspectionProfiles } from './inspectionProfileSelection'

export type NormalInspectionPurpose =
  | 'basic_health'
  | 'simulation_readiness'
  | 'export_preflight'
  | 'assembly_consistency'
  | 'hardware_config'

export interface NormalInspectionPlanOverride {
  purpose?: NormalInspectionPurpose
  targetPlatform?: InspectionTargetPlatform
  sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
  robotType?: InspectionRobotType
}

export interface NormalInspectionPlanExcludedProfile {
  profileId: string
  reason: Exclude<InspectionApplicabilityStatus, 'applicable'>
}

export interface NormalInspectionPlan {
  purpose: NormalInspectionPurpose
  targetPlatform: InspectionTargetPlatform
  recommendation: InspectionProfileRecommendation
  selectedProfiles: SelectedInspectionProfiles
  includedProfileIds: string[]
  excludedProfiles: NormalInspectionPlanExcludedProfile[]
  reasons: string[]
}

export interface BuildNormalInspectionPlanOptions {
  robot: RobotState
  workflowContext?: InspectionWorkflowRecommendationContext
  override?: NormalInspectionPlanOverride
}

const TARGET_PLATFORM_PROFILE_IDS: Partial<Record<InspectionTargetPlatform, string>> = {
  ros_control: 'target.ros_control',
  gazebo: 'target.gazebo',
  mujoco: 'target.mujoco',
  isaac_sim: 'target.isaac_sim',
  export_portability: 'target.export_portability',
}

const PURPOSE_PROFILE_IDS: Partial<Record<NormalInspectionPurpose, string[]>> = {
  export_preflight: ['workflow.export_preflight', 'target.export_portability'],
  assembly_consistency: ['workflow.assembly'],
  hardware_config: ['workflow.hardware_config'],
}

const addProfileId = (profileIds: string[], profileId: string | undefined) => {
  if (!profileId || profileIds.includes(profileId) || !getInspectionProfileDefinition(profileId)) {
    return
  }

  profileIds.push(profileId)
}

const hasHardwareConfig = (robot: RobotState) =>
  Object.values(robot.joints).some((joint) =>
    Boolean(joint.hardware?.motorType || joint.hardware?.motorId || joint.hardware?.armature),
  )

const inferTargetPlatform = (
  robot: RobotState,
  workflowContext?: InspectionWorkflowRecommendationContext,
): InspectionTargetPlatform => {
  if (workflowContext?.exportTargetFormat === 'mjcf') {
    return 'mujoco'
  }
  if (workflowContext?.exportTargetFormat === 'sdf') {
    return 'gazebo'
  }
  if (workflowContext?.exportTargetFormat === 'usd') {
    return 'isaac_sim'
  }

  const sourceFormat = robot.inspectionContext?.sourceFormat
  if (sourceFormat === 'mjcf') {
    return 'mujoco'
  }
  if (sourceFormat === 'sdf') {
    return 'gazebo'
  }
  if (sourceFormat === 'usd') {
    return 'isaac_sim'
  }
  if (hasHardwareConfig(robot)) {
    return 'ros_control'
  }

  return 'generic'
}

const inferPurpose = (
  robot: RobotState,
  workflowContext?: InspectionWorkflowRecommendationContext,
): NormalInspectionPurpose => {
  if (
    workflowContext?.assemblyActive ||
    (workflowContext?.componentCount ?? 0) > 1 ||
    (workflowContext?.bridgeCount ?? 0) > 0
  ) {
    return 'assembly_consistency'
  }

  if (hasHardwareConfig(robot)) {
    return 'hardware_config'
  }

  if (workflowContext?.exportRequested || workflowContext?.exportTargetFormat) {
    return 'export_preflight'
  }

  if (
    robot.inspectionContext?.sourceFormat === 'mjcf' ||
    robot.inspectionContext?.sourceFormat === 'sdf' ||
    robot.inspectionContext?.sourceFormat === 'usd' ||
    workflowContext?.collisionEdited ||
    workflowContext?.inertiaEdited
  ) {
    return 'simulation_readiness'
  }

  return 'basic_health'
}

const buildReasonCodes = (
  robot: RobotState,
  purpose: NormalInspectionPurpose,
  targetPlatform: InspectionTargetPlatform,
  override: NormalInspectionPlanOverride | undefined,
  workflowContext?: InspectionWorkflowRecommendationContext,
) => {
  const reasons: string[] = []
  const sourceFormat = override?.sourceFormat ?? robot.inspectionContext?.sourceFormat

  if (sourceFormat) {
    reasons.push(`source_format:${sourceFormat}`)
  }
  if (purpose !== 'basic_health') {
    reasons.push(`purpose:${purpose}`)
  }
  if (targetPlatform !== 'generic') {
    reasons.push(`target:${targetPlatform}`)
  }
  if (
    workflowContext?.assemblyActive ||
    (workflowContext?.componentCount ?? 0) > 1 ||
    (workflowContext?.bridgeCount ?? 0) > 0
  ) {
    reasons.push('workflow:assembly')
  }
  if (hasHardwareConfig(robot)) {
    reasons.push('workflow:hardware_config')
  }
  if (workflowContext?.exportRequested || workflowContext?.exportTargetFormat) {
    reasons.push('workflow:export_preflight')
  }
  if (workflowContext?.collisionEdited) {
    reasons.push('workflow:collision_authoring')
  }
  if (workflowContext?.inertiaEdited) {
    reasons.push('workflow:inertia_authoring')
  }

  return reasons
}

export function buildNormalInspectionPlan({
  robot,
  workflowContext,
  override,
}: BuildNormalInspectionPlanOptions): NormalInspectionPlan {
  const targetPlatform = override?.targetPlatform ?? inferTargetPlatform(robot, workflowContext)
  const purpose = override?.purpose ?? inferPurpose(robot, workflowContext)
  const applicabilityOverride = {
    sourceFormat: override?.sourceFormat,
    robotTypes: override?.robotType ? [override.robotType] : undefined,
  }
  const recommendation = buildInspectionProfileRecommendation(robot, {
    targetPlatform,
    sourceFormat: override?.sourceFormat,
    robotType: override?.robotType,
    workflowContext,
  })
  const candidateProfileIds = [...recommendation.profileIds]

  PURPOSE_PROFILE_IDS[purpose]?.forEach((profileId) => addProfileId(candidateProfileIds, profileId))
  addProfileId(candidateProfileIds, TARGET_PLATFORM_PROFILE_IDS[targetPlatform])

  const selectedProfiles: SelectedInspectionProfiles = {}
  const excludedProfiles: NormalInspectionPlanExcludedProfile[] = []

  INSPECTION_PROFILE_DEFINITIONS.forEach((profile) => {
    const profileApplicability = isInspectionItemApplicable(
      robot,
      profile.id,
      undefined,
      applicabilityOverride,
    )
    if (profileApplicability !== 'applicable') {
      excludedProfiles.push({
        profileId: profile.id,
        reason: profileApplicability,
      })
    }
  })

  candidateProfileIds.forEach((profileId) => {
    const profile = getInspectionProfileDefinition(profileId)
    if (!profile) {
      return
    }

    const selectedItems = profile.items.filter(
      (item) =>
        isInspectionItemApplicable(robot, profile.id, item.id, applicabilityOverride) ===
        'applicable',
    )
    if (selectedItems.length > 0) {
      selectedProfiles[profile.id] = new Set(selectedItems.map((item) => item.id))
    }
  })

  return {
    purpose,
    targetPlatform,
    recommendation,
    selectedProfiles,
    includedProfileIds: Object.entries(selectedProfiles)
      .filter(([, itemIds]) => itemIds.size > 0)
      .map(([profileId]) => profileId),
    excludedProfiles,
    reasons: buildReasonCodes(robot, purpose, targetPlatform, override, workflowContext),
  }
}

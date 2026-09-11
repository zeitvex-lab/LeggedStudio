import { GeometryType, JointType, type RobotState, type UrdfVisual } from '@/types'
import { getInspectionProfileDefinition } from '../config/inspectionProfiles'

export type InspectionRobotType =
  | 'generic'
  | 'humanoid'
  | 'quadruped'
  | 'manipulator'
  | 'mobile_base'
  | 'gripper'

export type InspectionRobotMorphology =
  | InspectionRobotType
  | 'biped'
  | 'dexterous_hand'
  | 'parallel_mechanism'

export type InspectionTargetPlatform =
  | 'generic'
  | 'ros_control'
  | 'gazebo'
  | 'mujoco'
  | 'isaac_sim'
  | 'export_portability'

export interface InspectionWorkflowRecommendationContext {
  assemblyActive?: boolean
  componentCount?: number
  bridgeCount?: number
  componentTransformAuthored?: boolean
  collisionEdited?: boolean
  inertiaEdited?: boolean
  exportRequested?: boolean
  exportTargetFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
}

export interface InspectionProfileRecommendation {
  sourceFormat: string
  robotType: InspectionRobotType
  robotTypes: InspectionRobotMorphology[]
  targetPlatform: InspectionTargetPlatform
  profileIds: string[]
  confidence: 'high' | 'medium' | 'low'
}

interface InspectionProfileRecommendationOptions {
  targetPlatform?: InspectionTargetPlatform
  sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
  robotType?: InspectionRobotType
  workflowContext?: InspectionWorkflowRecommendationContext
}

const BASE_PROFILE_IDS = [
  'base.robot_model',
  'base.physical_plausibility',
  'base.simulation_readiness',
  'base.maintainability',
]

const SOURCE_FORMAT_PROFILE_IDS: Record<string, string> = {
  urdf: 'format.urdf',
  mjcf: 'format.mjcf',
  xacro: 'format.xacro',
  sdf: 'format.sdf',
  usd: 'format.usd',
  mesh: 'format.mesh_asset',
}

const addProfileIfDefined = (profileIds: string[], profileId: string | undefined) => {
  if (!profileId || profileIds.includes(profileId) || !getInspectionProfileDefinition(profileId)) {
    return
  }

  profileIds.push(profileId)
}

const hasHardwareConfig = (robot: RobotState) => {
  return Object.values(robot.joints).some((joint) => {
    const hardware = joint.hardware
    return Boolean(hardware?.motorType || hardware?.motorId || hardware?.armature)
  })
}

const buildRobotNameCorpus = (robot: RobotState) => {
  return [
    robot.name,
    ...Object.values(robot.links).map((link) => link.name || link.id),
    ...Object.values(robot.joints).map((joint) => joint.name || joint.id),
  ]
    .join(' ')
    .toLowerCase()
}

const addMorphology = (
  robotTypes: InspectionRobotMorphology[],
  robotType: InspectionRobotMorphology,
) => {
  if (!robotTypes.includes(robotType)) {
    robotTypes.push(robotType)
  }
}

const geometryList = (robot: RobotState) => {
  return Object.values(robot.links).flatMap((link) => [
    link.visual,
    ...(link.visualBodies ?? []),
    link.collision,
    ...(link.collisionBodies ?? []),
  ])
}

const collisionGeometryList = (robot: RobotState) => {
  return Object.values(robot.links).flatMap((link) => [
    link.collision,
    ...(link.collisionBodies ?? []),
  ])
}

const isMeshGeometry = (geometry: UrdfVisual | undefined) => {
  return Boolean(
    geometry &&
      (geometry.type === GeometryType.MESH ||
        geometry.meshPath ||
        geometry.mjcfMesh ||
        (geometry.usdMeshDescriptors?.length ?? 0) > 0),
  )
}

const hasMeshGeometry = (robot: RobotState) => {
  return geometryList(robot).some(isMeshGeometry)
}

const hasCollisionMeshGeometry = (robot: RobotState) => {
  return collisionGeometryList(robot).some(isMeshGeometry)
}

const hasMissingCollisionGeometry = (robot: RobotState) => {
  return Object.values(robot.links).some((link) => {
    const collisionBodies = link.collisionBodies ?? []
    return link.collision.type === GeometryType.NONE && collisionBodies.length === 0
  })
}

const hasComplexCollisionAuthoringSignal = (robot: RobotState, corpus: string) => {
  return (
    hasMissingCollisionGeometry(robot) ||
    hasCollisionMeshGeometry(robot) ||
    Object.values(robot.links).some((link) => (link.collisionBodies?.length ?? 0) > 1) ||
    /(foot|feet|wheel|finger|gripper|claw|toe|sole|caster)/.test(corpus)
  )
}

const hasInvalidInertia = (robot: RobotState) => {
  return Object.values(robot.links).some((link) => {
    const inertial = link.inertial
    if (!inertial) {
      return true
    }

    const { ixx, iyy, izz } = inertial.inertia
    return (
      inertial.mass <= 0 ||
      ixx <= 0 ||
      iyy <= 0 ||
      izz <= 0 ||
      ixx + iyy < izz ||
      ixx + izz < iyy ||
      iyy + izz < ixx
    )
  })
}

const hasAssemblyWorkflowSignal = (context?: InspectionWorkflowRecommendationContext) => {
  return Boolean(
    context?.assemblyActive ||
      (context?.componentCount ?? 0) > 1 ||
      (context?.bridgeCount ?? 0) > 0 ||
      context?.componentTransformAuthored,
  )
}

const hasExportWorkflowSignal = (
  sourceFormat: string,
  context?: InspectionWorkflowRecommendationContext,
) => {
  return Boolean(
    context?.exportRequested ||
      (context?.exportTargetFormat && context.exportTargetFormat !== sourceFormat),
  )
}

export function inferInspectionRobotTypes(robot: RobotState): InspectionRobotMorphology[] {
  const corpus = buildRobotNameCorpus(robot)
  const robotTypes: InspectionRobotMorphology[] = []

  if (
    /\b(fl|fr|rl|rr)[_-]/.test(corpus) ||
    /(quadruped|go1|go2|aliengo|a1|front_left|front_right|rear_left|rear_right|hind|calf)/.test(
      corpus,
    )
  ) {
    addMorphology(robotTypes, 'quadruped')
  }

  if (
    /(humanoid|biped|pelvis|waist|torso)/.test(corpus) ||
    (/(^|\s)(left|right|l|r)[_-]/.test(corpus) && /(leg|arm|hip|shoulder)/.test(corpus))
  ) {
    addMorphology(robotTypes, 'humanoid')
  }

  if (
    /(biped|left_.*(leg|hip|knee|ankle|foot)|right_.*(leg|hip|knee|ankle|foot)|l_.*(leg|hip|knee|ankle|foot)|r_.*(leg|hip|knee|ankle|foot))/.test(
      corpus,
    ) ||
    (robotTypes.includes('humanoid') && /(leg|hip|knee|ankle|foot)/.test(corpus))
  ) {
    addMorphology(robotTypes, 'biped')
  }

  if (/(manipulator|robot_arm|shoulder|elbow|wrist|six_axis|6axis)/.test(corpus)) {
    addMorphology(robotTypes, 'manipulator')
  }

  const continuousWheelJoints = Object.values(robot.joints).filter(
    (joint) => joint.type === JointType.CONTINUOUS && /(wheel|caster)/.test(joint.name || joint.id),
  )
  if (
    /(wheel|caster|mobile_base|diff_drive|omni)/.test(corpus) ||
    continuousWheelJoints.length >= 2
  ) {
    addMorphology(robotTypes, 'mobile_base')
  }

  if (
    /(gripper|finger|claw|jaw|end_effector)/.test(corpus) ||
    Object.values(robot.joints).some((joint) => Boolean(joint.mimic))
  ) {
    addMorphology(robotTypes, 'gripper')
  }

  if (
    /(dexterous|thumb|index|middle|ring|little|palm)/.test(corpus) ||
    (corpus.match(/finger/g) ?? []).length >= 3 ||
    (robot.inspectionContext?.mjcf?.tendons.length ?? 0) >= 3
  ) {
    addMorphology(robotTypes, 'dexterous_hand')
  }

  if (
    (robot.closedLoopConstraints?.length ?? 0) > 0 ||
    /(parallel|fourbar|four_bar|four-bar|delta|linkage|closed_loop|closed-loop)/.test(corpus)
  ) {
    addMorphology(robotTypes, 'parallel_mechanism')
  }

  return robotTypes.length ? robotTypes : ['generic']
}

export function inferInspectionRobotType(robot: RobotState): InspectionRobotType {
  const robotTypes = inferInspectionRobotTypes(robot)
  const primaryOrder: InspectionRobotType[] = [
    'quadruped',
    'humanoid',
    'manipulator',
    'mobile_base',
    'gripper',
  ]

  return primaryOrder.find((robotType) => robotTypes.includes(robotType)) ?? 'generic'
}

export function buildInspectionProfileRecommendation(
  robot: RobotState,
  options: InspectionProfileRecommendationOptions = {},
): InspectionProfileRecommendation {
  const sourceFormat = options.sourceFormat ?? robot.inspectionContext?.sourceFormat ?? 'urdf'
  const inferredRobotTypes = inferInspectionRobotTypes(robot)
  const robotTypes = options.robotType ? [options.robotType] : inferredRobotTypes
  const robotType = options.robotType ?? inferInspectionRobotType(robot)
  const corpus = buildRobotNameCorpus(robot)
  const profileIds: string[] = []

  BASE_PROFILE_IDS.forEach((profileId) => addProfileIfDefined(profileIds, profileId))
  addProfileIfDefined(profileIds, SOURCE_FORMAT_PROFILE_IDS[sourceFormat])

  if (hasMeshGeometry(robot)) {
    addProfileIfDefined(profileIds, 'format.mesh_asset')
  }

  if (hasHardwareConfig(robot)) {
    addProfileIfDefined(profileIds, 'workflow.hardware_config')
  }

  if (robotTypes.includes('humanoid')) {
    addProfileIfDefined(profileIds, 'morph.humanoid')
  }
  if (robotTypes.includes('biped')) {
    addProfileIfDefined(profileIds, 'morph.biped')
  }
  if (robotTypes.includes('quadruped')) {
    addProfileIfDefined(profileIds, 'morph.quadruped')
  }
  if (robotTypes.includes('manipulator')) {
    addProfileIfDefined(profileIds, 'morph.manipulator')
  }
  if (robotTypes.includes('mobile_base')) {
    addProfileIfDefined(profileIds, 'morph.mobile_base')
  }
  if (robotTypes.includes('gripper')) {
    addProfileIfDefined(profileIds, 'morph.gripper')
  }
  if (robotTypes.includes('dexterous_hand')) {
    addProfileIfDefined(profileIds, 'morph.dexterous_hand')
  }
  if (robotTypes.includes('parallel_mechanism')) {
    addProfileIfDefined(profileIds, 'morph.parallel_mechanism')
  }

  if (hasAssemblyWorkflowSignal(options.workflowContext)) {
    addProfileIfDefined(profileIds, 'workflow.assembly')
  }
  if (
    options.workflowContext?.collisionEdited ||
    hasComplexCollisionAuthoringSignal(robot, corpus)
  ) {
    addProfileIfDefined(profileIds, 'workflow.collision_authoring')
  }
  if (options.workflowContext?.inertiaEdited || hasInvalidInertia(robot)) {
    addProfileIfDefined(profileIds, 'workflow.inertia_authoring')
  }
  if (hasExportWorkflowSignal(sourceFormat, options.workflowContext)) {
    addProfileIfDefined(profileIds, 'workflow.export_preflight')
  }

  return {
    sourceFormat,
    robotType,
    robotTypes,
    targetPlatform: options.targetPlatform ?? 'generic',
    profileIds,
    confidence:
      robot.inspectionContext?.sourceFormat || robotTypes.some((type) => type !== 'generic')
        ? 'high'
        : 'medium',
  }
}

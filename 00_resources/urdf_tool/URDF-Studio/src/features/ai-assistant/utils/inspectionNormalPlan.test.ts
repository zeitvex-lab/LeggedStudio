import test from 'node:test'
import assert from 'node:assert/strict'

import { GeometryType, JointType, type RobotState } from '@/types'
import {
  buildNormalInspectionPlan,
  type NormalInspectionPlanOverride,
} from './inspectionNormalPlan.ts'
import type { InspectionWorkflowRecommendationContext } from './inspectionProfileRecommendation.ts'

const createRobot = (
  name: string,
  options: {
    links?: string[]
    joints?: string[]
    sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
    hardware?: boolean
    meshCollision?: boolean
  } = {},
): RobotState => {
  const linkNames = options.links ?? ['base_link']
  const jointNames = options.joints ?? []

  return {
    name,
    rootLinkId: linkNames[0],
    links: Object.fromEntries(
      linkNames.map((linkName) => [
        linkName,
        {
          id: linkName,
          name: linkName,
          visual: {
            type: GeometryType.BOX,
            dimensions: { x: 0.1, y: 0.1, z: 0.1 },
            origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
            color: '#999999',
          },
          collision: options.meshCollision
            ? {
                type: GeometryType.MESH,
                meshPath: `${linkName}.stl`,
                scale: { x: 1, y: 1, z: 1 },
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
                color: '#999999',
              }
            : {
                type: GeometryType.BOX,
                dimensions: { x: 0.1, y: 0.1, z: 0.1 },
                origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
                color: '#999999',
              },
        },
      ]),
    ),
    joints: Object.fromEntries(
      jointNames.map((jointName, index) => [
        jointName,
        {
          id: jointName,
          name: jointName,
          type: JointType.REVOLUTE,
          parentLinkId: linkNames[index] ?? linkNames[0],
          childLinkId: linkNames[index + 1] ?? linkNames[0],
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          axis: { x: 0, y: 0, z: 1 },
          limit: { lower: -1, upper: 1, effort: 10, velocity: 5 },
          dynamics: { damping: 0, friction: 0 },
          hardware: options.hardware
            ? {
                armature: 0.01,
                motorType: 'servo',
                motorId: `M${index + 1}`,
                motorDirection: 1,
              }
            : undefined,
        },
      ]),
    ),
    inspectionContext: options.sourceFormat ? { sourceFormat: options.sourceFormat } : undefined,
    selection: null,
  } as unknown as RobotState
}

const profileIds = (plan: ReturnType<typeof buildNormalInspectionPlan>) =>
  Object.keys(plan.selectedProfiles).filter((profileId) => plan.selectedProfiles[profileId].size > 0)

test('buildNormalInspectionPlan infers MuJoCo target from MJCF source', () => {
  const plan = buildNormalInspectionPlan({
    robot: createRobot('go2_quadruped', {
      sourceFormat: 'mjcf',
      links: ['base', 'fl_thigh', 'fr_thigh', 'rl_calf', 'rr_calf'],
      joints: ['fl_hip', 'fr_hip', 'rl_hip', 'rr_hip'],
    }),
  })

  assert.equal(plan.purpose, 'simulation_readiness')
  assert.equal(plan.targetPlatform, 'mujoco')
  assert.ok(profileIds(plan).includes('format.mjcf'))
  assert.ok(profileIds(plan).includes('target.mujoco'))
  assert.ok(profileIds(plan).includes('morph.quadruped'))
  assert.ok(plan.reasons.includes('source_format:mjcf'))
})

test('buildNormalInspectionPlan infers Gazebo target from SDF source', () => {
  const plan = buildNormalInspectionPlan({
    robot: createRobot('gazebo_model', {
      sourceFormat: 'sdf',
      joints: ['base_joint'],
    }),
  })

  assert.equal(plan.targetPlatform, 'gazebo')
  assert.ok(profileIds(plan).includes('format.sdf'))
  assert.ok(profileIds(plan).includes('target.gazebo'))
})

test('buildNormalInspectionPlan prioritizes assembly workflow context', () => {
  const workflowContext: InspectionWorkflowRecommendationContext = {
    assemblyActive: true,
    componentCount: 2,
    bridgeCount: 1,
  }
  const plan = buildNormalInspectionPlan({
    robot: createRobot('assembly_robot', { sourceFormat: 'urdf', joints: ['base_joint'] }),
    workflowContext,
  })

  assert.equal(plan.purpose, 'assembly_consistency')
  assert.ok(profileIds(plan).includes('workflow.assembly'))
  assert.ok(plan.reasons.includes('workflow:assembly'))
})

test('buildNormalInspectionPlan detects hardware configuration purpose', () => {
  const plan = buildNormalInspectionPlan({
    robot: createRobot('servo_arm', {
      sourceFormat: 'urdf',
      joints: ['shoulder_pan', 'elbow_pitch', 'wrist_roll'],
      links: ['base_link', 'shoulder_link', 'elbow_link', 'wrist_link'],
      hardware: true,
    }),
  })

  assert.equal(plan.purpose, 'hardware_config')
  assert.ok(profileIds(plan).includes('workflow.hardware_config'))
  assert.ok(plan.reasons.includes('workflow:hardware_config'))
})

test('buildNormalInspectionPlan lets overrides correct purpose and target platform', () => {
  const override: NormalInspectionPlanOverride = {
    purpose: 'export_preflight',
    targetPlatform: 'gazebo',
  }
  const plan = buildNormalInspectionPlan({
    robot: createRobot('go2_quadruped', {
      sourceFormat: 'mjcf',
      links: ['base', 'fl_thigh', 'fr_thigh', 'rl_calf', 'rr_calf'],
      joints: ['fl_hip', 'fr_hip', 'rl_hip', 'rr_hip'],
    }),
    override,
  })

  assert.equal(plan.purpose, 'export_preflight')
  assert.equal(plan.targetPlatform, 'gazebo')
  assert.ok(profileIds(plan).includes('workflow.export_preflight'))
  assert.ok(profileIds(plan).includes('target.gazebo'))
  assert.equal(profileIds(plan).includes('target.mujoco'), false)
})

test('buildNormalInspectionPlan excludes non-applicable recommended profiles', () => {
  const plan = buildNormalInspectionPlan({
    robot: createRobot('usd_robot', { sourceFormat: 'usd', joints: ['base_joint'] }),
  })

  assert.equal(profileIds(plan).includes('format.urdf'), false)
  assert.equal(
    plan.excludedProfiles.some(
      (entry) => entry.profileId === 'format.urdf' && entry.reason === 'not_applicable',
    ),
    true,
  )
})

import test from 'node:test'
import assert from 'node:assert/strict'

import { GeometryType, JointType, type RobotState } from '@/types'
import { buildInspectionProfileRecommendation } from './inspectionProfileRecommendation.ts'

const createRobot = (
  name: string,
  names: {
    links?: string[]
    joints?: string[]
    sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
  } = {},
): RobotState => {
  const linkNames = names.links ?? ['base_link']
  const jointNames = names.joints ?? []
  const links = Object.fromEntries(
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
        collision: {
          type: GeometryType.BOX,
          dimensions: { x: 0.1, y: 0.1, z: 0.1 },
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          color: '#999999',
        },
      },
    ]),
  )
  const joints = Object.fromEntries(
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
        hardware: {
          armature: 0.01,
          motorType: 'servo',
          motorId: `M${index + 1}`,
          motorDirection: 1,
        },
      },
    ]),
  )

  return {
    name,
    links,
    joints,
    rootLinkId: linkNames[0] ?? 'base_link',
    inspectionContext: names.sourceFormat
      ? {
          sourceFormat: names.sourceFormat,
        }
      : undefined,
    selection: null,
  } as unknown as RobotState
}

test('buildInspectionProfileRecommendation includes URDF format and base profiles by default', () => {
  const recommendation = buildInspectionProfileRecommendation(
    createRobot('generic_bot', {
      sourceFormat: 'urdf',
      joints: ['base_to_body'],
    }),
  )

  assert.equal(recommendation.sourceFormat, 'urdf')
  assert.equal(recommendation.robotType, 'generic')
  assert.equal(recommendation.targetPlatform, 'generic')
  assert.ok(recommendation.profileIds.includes('format.urdf'))
  assert.ok(recommendation.profileIds.includes('base.robot_model'))
  assert.ok(recommendation.profileIds.includes('workflow.hardware_config'))
})

test('buildInspectionProfileRecommendation detects humanoid models and includes humanoid profile', () => {
  const recommendation = buildInspectionProfileRecommendation(
    createRobot('humanoid_biped', {
      sourceFormat: 'urdf',
      links: ['pelvis', 'waist_link', 'left_leg_link', 'right_arm_link'],
      joints: ['waist_yaw', 'left_hip_pitch', 'right_shoulder_pitch'],
    }),
  )

  assert.equal(recommendation.robotType, 'humanoid')
  assert.equal(recommendation.confidence, 'high')
  assert.ok(recommendation.profileIds.includes('morph.humanoid'))
})

test('buildInspectionProfileRecommendation detects quadruped and manipulator shapes without forcing humanoid checks', () => {
  const quadruped = buildInspectionProfileRecommendation(
    createRobot('go2_quadruped', {
      sourceFormat: 'mjcf',
      links: ['base', 'fl_thigh', 'fr_thigh', 'rl_calf', 'rr_calf'],
      joints: ['fl_hip', 'fr_hip', 'rl_hip', 'rr_hip'],
    }),
  )
  const manipulator = buildInspectionProfileRecommendation(
    createRobot('six_axis_arm', {
      sourceFormat: 'urdf',
      links: ['base_link', 'shoulder_link', 'elbow_link', 'wrist_link', 'gripper_link'],
      joints: ['shoulder_pan', 'elbow_pitch', 'wrist_roll'],
    }),
  )

  assert.equal(quadruped.sourceFormat, 'mjcf')
  assert.equal(quadruped.robotType, 'quadruped')
  assert.ok(quadruped.profileIds.includes('format.mjcf'))
  assert.ok(quadruped.profileIds.includes('morph.quadruped'))
  assert.equal(quadruped.profileIds.includes('morph.humanoid'), false)
  assert.equal(manipulator.robotType, 'manipulator')
  assert.ok(manipulator.profileIds.includes('morph.manipulator'))
  assert.equal(manipulator.profileIds.includes('morph.humanoid'), false)
})

test('buildInspectionProfileRecommendation maps expanded source formats to format profiles', () => {
  assert.ok(
    buildInspectionProfileRecommendation(
      createRobot('xacro_bot', { sourceFormat: 'xacro', joints: ['base_joint'] }),
    ).profileIds.includes('format.xacro'),
  )
  assert.ok(
    buildInspectionProfileRecommendation(
      createRobot('sdf_bot', { sourceFormat: 'sdf', joints: ['base_joint'] }),
    ).profileIds.includes('format.sdf'),
  )
  assert.ok(
    buildInspectionProfileRecommendation(
      createRobot('usd_bot', { sourceFormat: 'usd', joints: ['base_joint'] }),
    ).profileIds.includes('format.usd'),
  )
})

test('buildInspectionProfileRecommendation recommends mesh asset checks for mesh-heavy models', () => {
  const meshSource = buildInspectionProfileRecommendation(
    createRobot('mesh_import', { sourceFormat: 'mesh' }),
  )
  const visualMeshRobot = createRobot('visual_mesh_robot')
  visualMeshRobot.links.base_link.visual.type = GeometryType.MESH
  visualMeshRobot.links.base_link.visual.meshPath = 'meshes/base_link.stl'
  const visualMesh = buildInspectionProfileRecommendation(visualMeshRobot)

  const collisionMeshRobot = createRobot('collision_mesh_robot')
  collisionMeshRobot.links.base_link.collision.type = GeometryType.MESH
  collisionMeshRobot.links.base_link.collision.meshPath = 'meshes/base_collision.obj'
  const collisionMesh = buildInspectionProfileRecommendation(collisionMeshRobot)

  assert.ok(meshSource.profileIds.includes('format.mesh_asset'))
  assert.ok(visualMesh.profileIds.includes('format.mesh_asset'))
  assert.ok(collisionMesh.profileIds.includes('format.mesh_asset'))
  assert.ok(collisionMesh.profileIds.includes('workflow.collision_authoring'))
})

test('buildInspectionProfileRecommendation supports multiple morphology profiles for one robot', () => {
  const humanoidBiped = buildInspectionProfileRecommendation(
    createRobot('humanoid_biped', {
      links: ['pelvis', 'left_hip_link', 'left_knee_link', 'left_foot_link', 'right_hip_link', 'right_knee_link', 'right_foot_link'],
      joints: ['left_hip_pitch', 'left_knee_pitch', 'left_ankle_pitch', 'right_hip_pitch', 'right_knee_pitch', 'right_ankle_pitch'],
    }),
  )
  const armWithGripper = buildInspectionProfileRecommendation(
    createRobot('six_axis_arm_with_gripper', {
      links: ['base_link', 'shoulder_link', 'elbow_link', 'wrist_link', 'left_finger_link', 'right_finger_link'],
      joints: ['shoulder_pan', 'elbow_pitch', 'wrist_roll', 'left_finger_joint', 'right_finger_joint'],
    }),
  )
  const dexterousHand = buildInspectionProfileRecommendation(
    createRobot('dexterous_hand', {
      links: ['palm', 'thumb_link', 'index_finger_link', 'middle_finger_link', 'ring_finger_link', 'little_finger_link'],
      joints: ['thumb_joint', 'index_joint', 'middle_joint', 'ring_joint', 'little_joint'],
    }),
  )

  assert.ok(humanoidBiped.profileIds.includes('morph.humanoid'))
  assert.ok(humanoidBiped.profileIds.includes('morph.biped'))
  assert.ok(armWithGripper.profileIds.includes('morph.manipulator'))
  assert.ok(armWithGripper.profileIds.includes('morph.gripper'))
  assert.ok(dexterousHand.profileIds.includes('morph.dexterous_hand'))
})

test('buildInspectionProfileRecommendation recommends parallel mechanism checks from closed-loop evidence', () => {
  const robot = createRobot('fourbar_linkage', {
    links: ['base', 'left_link', 'right_link'],
    joints: ['left_joint', 'right_joint'],
  })
  robot.closedLoopConstraints = [
    {
      id: 'loop_constraint',
      type: 'connect',
      linkAId: 'left_link',
      linkBId: 'right_link',
      anchorWorld: { x: 0, y: 0, z: 0 },
      anchorLocalA: { x: 0, y: 0, z: 0 },
      anchorLocalB: { x: 0, y: 0, z: 0 },
    },
  ]

  const recommendation = buildInspectionProfileRecommendation(robot)

  assert.ok(recommendation.profileIds.includes('morph.parallel_mechanism'))
})

test('buildInspectionProfileRecommendation recommends workflow profiles from model and workflow context', () => {
  const robot = createRobot('workflow_robot', {
    links: ['base_link', 'foot_link'],
    joints: ['ankle_joint'],
  })
  robot.links.base_link.collision.type = GeometryType.NONE
  delete robot.links.foot_link.inertial

  const recommendation = buildInspectionProfileRecommendation(robot, {
    workflowContext: {
      assemblyActive: true,
      bridgeCount: 1,
      exportRequested: true,
    },
  })

  assert.ok(recommendation.profileIds.includes('workflow.assembly'))
  assert.ok(recommendation.profileIds.includes('workflow.collision_authoring'))
  assert.ok(recommendation.profileIds.includes('workflow.inertia_authoring'))
  assert.ok(recommendation.profileIds.includes('workflow.export_preflight'))
  assert.equal(recommendation.profileIds.some((profileId) => profileId.startsWith('target.')), false)
})

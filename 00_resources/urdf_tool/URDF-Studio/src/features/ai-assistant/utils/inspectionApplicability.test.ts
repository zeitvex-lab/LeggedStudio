import test from 'node:test'
import assert from 'node:assert/strict'

import { GeometryType, JointType, type RobotState } from '@/types'
import { isInspectionItemApplicable } from './inspectionApplicability.ts'

const createRobot = (
  name: string,
  names: {
    links: string[]
    joints: string[]
    sourceFormat?: NonNullable<RobotState['inspectionContext']>['sourceFormat']
  },
): RobotState =>
  ({
    name,
    rootLinkId: names.links[0],
    links: Object.fromEntries(
      names.links.map((linkName) => [
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
    ),
    joints: Object.fromEntries(
      names.joints.map((jointName) => [
        jointName,
        {
          id: jointName,
          name: jointName,
          type: JointType.REVOLUTE,
          parentLinkId: names.links[0],
          childLinkId: names.links[1] ?? names.links[0],
          origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
          axis: { x: 0, y: 0, z: 1 },
          limit: { lower: -1, upper: 1, effort: 10, velocity: 5 },
          dynamics: { damping: 0, friction: 0 },
          hardware: { armature: 0.01, motorType: 'servo', motorId: 'M1', motorDirection: 1 },
        },
      ]),
    ),
    inspectionContext: names.sourceFormat ? { sourceFormat: names.sourceFormat } : undefined,
    selection: null,
  }) as unknown as RobotState

test('isInspectionItemApplicable excludes humanoid-only checks for manipulators', () => {
  const manipulator = createRobot('six_axis_arm', {
    links: ['base_link', 'shoulder_link', 'elbow_link', 'wrist_link'],
    joints: ['shoulder_pan', 'elbow_pitch', 'wrist_roll'],
    sourceFormat: 'urdf',
  })

  assert.equal(
    isInspectionItemApplicable(manipulator, 'morph.humanoid', 'waist_centering'),
    'not_applicable',
  )
})

test('isInspectionItemApplicable enables quadruped and mjcf profile checks only when matching context exists', () => {
  const quadruped = createRobot('go2_quadruped', {
    links: ['base', 'fl_thigh', 'fr_thigh', 'rl_calf', 'rr_calf'],
    joints: ['fl_hip', 'fr_hip', 'rl_hip', 'rr_hip'],
    sourceFormat: 'mjcf',
  })

  assert.equal(
    isInspectionItemApplicable(quadruped, 'morph.quadruped', 'quadruped_leg_quads'),
    'applicable',
  )
  assert.equal(
    isInspectionItemApplicable(quadruped, 'format.mjcf', 'mjcf_root_model'),
    'applicable',
  )
  assert.equal(
    isInspectionItemApplicable(quadruped, 'format.urdf', 'urdf_robot_root'),
    'not_applicable',
  )
})

test('isInspectionItemApplicable marks expanded source profiles as insufficient without source context', () => {
  const robotWithoutSource = createRobot('source_unknown', {
    links: ['base_link'],
    joints: [],
  })
  const usdRobot = createRobot('usd_robot', {
    links: ['base_link'],
    joints: [],
    sourceFormat: 'usd',
  })

  assert.equal(
    isInspectionItemApplicable(robotWithoutSource, 'format.usd', 'usd_stage_root'),
    'insufficient_evidence',
  )
  assert.equal(
    isInspectionItemApplicable(usdRobot, 'format.usd', 'usd_stage_root'),
    'applicable',
  )
  assert.equal(
    isInspectionItemApplicable(usdRobot, 'format.sdf', 'sdf_root_version'),
    'not_applicable',
  )
})

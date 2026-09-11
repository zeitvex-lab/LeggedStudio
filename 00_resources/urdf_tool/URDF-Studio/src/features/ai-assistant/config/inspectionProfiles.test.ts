import test from 'node:test'
import assert from 'node:assert/strict'

import { INSPECTION_PROFILE_DEFINITIONS } from './inspectionProfiles.ts'

test('inspection profile definitions use unique ids', () => {
  const profileIds = INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id)

  assert.equal(new Set(profileIds).size, profileIds.length)
})

test('inspection profile definitions include executable items for each profile', () => {
  INSPECTION_PROFILE_DEFINITIONS.forEach((profile) => {
    assert.ok(profile.items.length > 0, `${profile.id} should define executable items`)

    const itemIds = profile.items.map((item) => item.id)
    assert.equal(new Set(itemIds).size, itemIds.length, `${profile.id} item ids should be unique`)
  })
})

test('inspection profile definitions do not retain legacy standard mappings', () => {
  INSPECTION_PROFILE_DEFINITIONS.forEach((profile) => {
    assert.equal('legacyItems' in profile, false, `${profile.id} should not expose legacyItems`)
    assert.equal('legacyMappings' in profile, false, `${profile.id} should not expose legacyMappings`)

    profile.items.forEach((item) => {
      assert.equal('legacyMapping' in item, false, `${profile.id}.${item.id} should not expose legacyMapping`)
    })
  })
})

test('inspection profile definitions include the full profile layers from the standard', () => {
  const profileIds = new Set(INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id))

  assert.ok(profileIds.has('base.robot_model'))
  assert.ok(profileIds.has('base.physical_plausibility'))
  assert.ok(profileIds.has('base.simulation_readiness'))
  assert.ok(profileIds.has('base.maintainability'))
  assert.ok(profileIds.has('morph.humanoid'))
  assert.ok(profileIds.has('morph.biped'))
  assert.ok(profileIds.has('morph.quadruped'))
  assert.ok(profileIds.has('morph.manipulator'))
  assert.ok(profileIds.has('morph.mobile_base'))
  assert.ok(profileIds.has('morph.gripper'))
  assert.ok(profileIds.has('morph.dexterous_hand'))
  assert.ok(profileIds.has('morph.parallel_mechanism'))
  assert.ok(profileIds.has('format.urdf'))
  assert.ok(profileIds.has('format.mjcf'))
  assert.ok(profileIds.has('format.xacro'))
  assert.ok(profileIds.has('format.sdf'))
  assert.ok(profileIds.has('format.usd'))
  assert.ok(profileIds.has('format.mesh_asset'))
  assert.ok(profileIds.has('target.ros_control'))
  assert.ok(profileIds.has('target.gazebo'))
  assert.ok(profileIds.has('target.mujoco'))
  assert.ok(profileIds.has('target.isaac_sim'))
  assert.ok(profileIds.has('target.export_portability'))
  assert.ok(profileIds.has('workflow.assembly'))
  assert.ok(profileIds.has('workflow.hardware_config'))
  assert.ok(profileIds.has('workflow.collision_authoring'))
  assert.ok(profileIds.has('workflow.inertia_authoring'))
  assert.ok(profileIds.has('workflow.export_preflight'))
})

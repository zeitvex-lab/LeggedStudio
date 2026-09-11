import assert from 'node:assert/strict'
import test from 'node:test'
import {
  areSelectedInspectionProfilesEqual,
  cloneSelectedInspectionProfiles,
  restoreInspectionProfileSelection,
  type SelectedInspectionProfiles,
} from './inspectionProfileSelection'

const selection = (entries: Record<string, string[]>): SelectedInspectionProfiles =>
  Object.fromEntries(
    Object.entries(entries).map(([profileId, itemIds]) => [profileId, new Set(itemIds)]),
  )

test('cloneSelectedInspectionProfiles creates independent item sets', () => {
  const original = selection({ 'base.robot_model': ['model_identity'] })
  const cloned = cloneSelectedInspectionProfiles(original)

  cloned['base.robot_model']?.add('tree_connectivity')

  assert.deepEqual(Array.from(original['base.robot_model'] ?? []), ['model_identity'])
  assert.deepEqual(Array.from(cloned['base.robot_model'] ?? []), [
    'model_identity',
    'tree_connectivity',
  ])
})

test('areSelectedInspectionProfilesEqual ignores set insertion order', () => {
  const left = selection({ 'base.robot_model': ['model_identity', 'tree_connectivity'] })
  const right = selection({ 'base.robot_model': ['tree_connectivity', 'model_identity'] })

  assert.equal(areSelectedInspectionProfilesEqual(left, right), true)
})

test('areSelectedInspectionProfilesEqual detects missing profiles and items', () => {
  const left = selection({ 'base.robot_model': ['model_identity'] })
  const right = selection({
    'base.robot_model': ['model_identity'],
    'format.urdf': ['urdf_robot_root'],
  })
  const changedItem = selection({ 'base.robot_model': ['tree_connectivity'] })

  assert.equal(areSelectedInspectionProfilesEqual(left, right), false)
  assert.equal(areSelectedInspectionProfilesEqual(left, changedItem), false)
})

test('restoreInspectionProfileSelection restores one recommended profile without mutating current', () => {
  const current = selection({
    'base.robot_model': ['model_identity'],
    'format.urdf': ['urdf_robot_root'],
  })
  const recommended = selection({
    'base.robot_model': ['tree_connectivity', 'reference_integrity'],
  })

  const restored = restoreInspectionProfileSelection(current, recommended, 'base.robot_model')

  assert.deepEqual(Array.from(restored['base.robot_model'] ?? []).sort(), [
    'reference_integrity',
    'tree_connectivity',
  ])
  assert.deepEqual(Array.from(restored['format.urdf'] ?? []), ['urdf_robot_root'])
  assert.deepEqual(Array.from(current['base.robot_model'] ?? []), ['model_identity'])
})

test('restoreInspectionProfileSelection clears profile when recommendation does not include it', () => {
  const current = selection({ 'format.urdf': ['urdf_robot_root'] })
  const recommended = selection({ 'base.robot_model': ['model_identity'] })

  const restored = restoreInspectionProfileSelection(current, recommended, 'format.urdf')

  assert.deepEqual(Array.from(restored['format.urdf'] ?? []), [])
  assert.deepEqual(Array.from(restored['base.robot_model'] ?? []), [])
})

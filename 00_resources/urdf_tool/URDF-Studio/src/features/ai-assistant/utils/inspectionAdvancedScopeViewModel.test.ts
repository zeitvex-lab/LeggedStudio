import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildInspectionItemScopeSummaries,
  buildInspectionLayerSummaries,
  buildInspectionProfileScopeSummaries,
  buildInspectionSelectionDeviation,
} from './inspectionAdvancedScopeViewModel'
import type { SelectedInspectionProfiles } from './inspectionProfileSelection'

const selection = (entries: Record<string, string[]>): SelectedInspectionProfiles =>
  Object.fromEntries(
    Object.entries(entries).map(([profileId, itemIds]) => [profileId, new Set(itemIds)]),
  )

test('buildInspectionSelectionDeviation reports added and removed items', () => {
  const selected = selection({
    'base.robot_model': ['model_identity'],
    'format.urdf': ['urdf_robot_root'],
  })
  const recommended = selection({
    'base.robot_model': ['model_identity', 'tree_connectivity'],
  })

  const deviation = buildInspectionSelectionDeviation(selected, recommended)

  assert.deepEqual(deviation.addedItems, [
    { profileId: 'format.urdf', itemId: 'urdf_robot_root' },
  ])
  assert.deepEqual(deviation.removedItems, [
    { profileId: 'base.robot_model', itemId: 'tree_connectivity' },
  ])
  assert.deepEqual(deviation.changedProfileIds.sort(), ['base.robot_model', 'format.urdf'])
  assert.equal(deviation.totalChangedItemCount, 2)
})

test('buildInspectionLayerSummaries groups counts by layer', () => {
  const selected = selection({
    'base.robot_model': ['model_identity'],
    'morph.quadruped': ['quadruped_leg_quads'],
  })
  const recommended = selection({
    'base.robot_model': ['model_identity', 'tree_connectivity'],
    'morph.quadruped': ['quadruped_leg_quads'],
  })

  const summaries = buildInspectionLayerSummaries(selected, recommended)
  const base = summaries.find((summary) => summary.layer === 'base')
  const morph = summaries.find((summary) => summary.layer === 'morph')

  assert.equal(base?.selectedItemCount, 1)
  assert.equal(base?.recommendedItemCount, 2)
  assert.equal(base?.totalItemCount, 20)
  assert.equal(morph?.selectedItemCount, 1)
  assert.equal(morph?.recommendedItemCount, 1)
})

test('buildInspectionProfileScopeSummaries classifies recommendation relations', () => {
  const selected = selection({
    'base.robot_model': ['model_identity'],
    'format.urdf': ['urdf_robot_root'],
  })
  const recommended = selection({
    'base.robot_model': ['model_identity', 'tree_connectivity'],
    'morph.quadruped': ['quadruped_leg_quads'],
  })

  const summaries = buildInspectionProfileScopeSummaries(selected, recommended)
  const base = summaries.find((summary) => summary.profileId === 'base.robot_model')
  const format = summaries.find((summary) => summary.profileId === 'format.urdf')
  const morph = summaries.find((summary) => summary.profileId === 'morph.quadruped')

  assert.equal(base?.relation, 'partial')
  assert.equal(format?.relation, 'user_added')
  assert.equal(morph?.relation, 'user_removed')
})

test('buildInspectionItemScopeSummaries marks user additions and removals', () => {
  const selected = selection({ 'base.robot_model': ['model_identity'] })
  const recommended = selection({ 'base.robot_model': ['tree_connectivity'] })

  const summaries = buildInspectionItemScopeSummaries('base.robot_model', selected, recommended)
  const selectedItem = summaries.find((summary) => summary.itemId === 'model_identity')
  const removedItem = summaries.find((summary) => summary.itemId === 'tree_connectivity')

  assert.equal(selectedItem?.relation, 'user_added')
  assert.equal(removedItem?.relation, 'user_removed')
})

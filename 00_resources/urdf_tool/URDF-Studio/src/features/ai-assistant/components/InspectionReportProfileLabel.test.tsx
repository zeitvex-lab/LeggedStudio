import test from 'node:test'
import assert from 'node:assert/strict'

import { buildInspectionIssueProfileLabel } from './InspectionReport.tsx'

test('buildInspectionIssueProfileLabel returns localized profile names', () => {
  assert.equal(
    buildInspectionIssueProfileLabel(
      {
        type: 'warning',
        title: 'Invalid mass',
        description: 'Mass must be positive.',
        profileId: 'base.physical_plausibility',
        itemId: 'mass_positive',
      },
      'zh',
    ),
    '通用物理合理性检查',
  )

  assert.equal(
    buildInspectionIssueProfileLabel(
      {
        type: 'warning',
        title: 'Invalid mass',
        description: 'Mass must be positive.',
        profileId: 'base.physical_plausibility',
        itemId: 'mass_positive',
      },
      'en',
    ),
    'Physical Plausibility',
  )
})

test('buildInspectionIssueProfileLabel returns null for unmapped profile ids', () => {
  assert.equal(
    buildInspectionIssueProfileLabel({
      type: 'warning',
      title: 'Invalid mass',
      description: 'Mass must be positive.',
      profileId: 'unmapped',
      itemId: 'unmapped',
    }),
    null,
  )
})

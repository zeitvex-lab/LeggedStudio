import test from 'node:test'
import assert from 'node:assert/strict'

import { processInspectionResults } from './processInspectionResults.ts'

test('processInspectionResults keeps valid profile issue ids and does not infer legacy fields', () => {
  const report = processInspectionResults(
    {
      summary: 'Inspection summary',
      issues: [
        {
          type: 'warning',
          title: 'Mass value is invalid',
          description: 'The base link mass should be greater than zero.',
          profileId: 'base.physical_plausibility',
          itemId: 'mass_positive',
          score: 4,
        },
      ],
    },
    {
      'base.physical_plausibility': ['mass_positive'],
    },
    'en',
  )

  const issue = report.issues[0]

  assert.equal(issue?.profileId, 'base.physical_plausibility')
  assert.equal(issue?.itemId, 'mass_positive')
  assert.equal('category' in (issue ?? {}), false)
  assert.equal('legacyCategoryId' in (issue ?? {}), false)
  assert.equal('legacyItemId' in (issue ?? {}), false)
  assert.deepEqual(report.profileScores, {
    'base.physical_plausibility': 4,
  })
  assert.equal('categoryScores' in report, false)
})

test('processInspectionResults rejects old category-only issues instead of mapping them', () => {
  const report = processInspectionResults(
    {
      summary: 'Inspection summary',
      issues: [
        {
          type: 'warning',
          title: 'Mass value is invalid',
          description: 'The base link mass should be greater than zero.',
          category: 'physical',
          itemId: 'mass_inertia_basic',
          score: 4,
        },
      ],
    },
    {
      'base.physical_plausibility': ['mass_positive'],
    },
    'en',
  )

  assert.equal(report.issues[0]?.profileId, 'unmapped')
  assert.equal(report.issues[0]?.itemId, 'unmapped')
  assert.equal(report.issues[0]?.type, 'error')
  assert.match(report.issues[0]?.description ?? '', /profileId/)
  assert.equal('legacyCategoryId' in (report.issues[0] ?? {}), false)
  assert.equal('categoryScores' in report, false)
})

test('processInspectionResults adds auto pass issues for selected profile items', () => {
  const report = processInspectionResults(
    {
      summary: 'Inspection summary',
      issues: [],
    },
    {
      'base.simulation_readiness': ['joint_limits_valid'],
    },
    'en',
  )

  assert.equal(report.issues[0]?.type, 'pass')
  assert.equal(report.issues[0]?.profileId, 'base.simulation_readiness')
  assert.equal(report.issues[0]?.itemId, 'joint_limits_valid')
  assert.equal('category' in (report.issues[0] ?? {}), false)
  assert.equal('legacyCategoryId' in (report.issues[0] ?? {}), false)
  assert.deepEqual(report.profileScores, {
    'base.simulation_readiness': 10,
  })
})

test('processInspectionResults reports total awarded score against selected max score', () => {
  const report = processInspectionResults(
    {
      summary: 'Inspection summary',
      issues: [
        {
          type: 'warning',
          title: 'Joint limit needs review',
          description: 'The joint limit is usable but close to an unsafe range.',
          profileId: 'base.simulation_readiness',
          itemId: 'joint_limits_valid',
          score: 7,
        },
      ],
    },
    {
      'base.simulation_readiness': ['joint_limits_valid', 'dynamics_parameters'],
    },
    'en',
  )

  assert.equal(report.overallScore, 17)
  assert.equal(report.maxScore, 20)
  assert.deepEqual(report.profileScores, {
    'base.simulation_readiness': 8.5,
  })
})

test('processInspectionResults ignores valid issues outside the selected inspection scope', () => {
  const report = processInspectionResults(
    {
      summary: 'Inspection summary',
      issues: [
        {
          type: 'warning',
          title: 'Selected joint limit issue',
          description: 'The selected joint limit item should remain in the report.',
          profileId: 'base.simulation_readiness',
          itemId: 'joint_limits_valid',
          score: 6,
        },
        {
          type: 'error',
          title: 'Unselected mass issue',
          description: 'This item was not selected by the user and should be ignored.',
          profileId: 'base.physical_plausibility',
          itemId: 'mass_positive',
          score: 0,
        },
      ],
    },
    {
      'base.simulation_readiness': ['joint_limits_valid'],
    },
    'en',
  )

  assert.equal(report.issues.length, 1)
  assert.equal(report.issues[0]?.profileId, 'base.simulation_readiness')
  assert.equal(report.issues[0]?.itemId, 'joint_limits_valid')
  assert.equal(report.overallScore, 6)
  assert.equal(report.maxScore, 10)
})

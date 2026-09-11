import test from 'node:test'
import assert from 'node:assert/strict'

import { buildInspectionCriteriaDescription } from './aiService.ts'

test('buildInspectionCriteriaDescription emits profile-only executable criteria', () => {
  const description = buildInspectionCriteriaDescription(
    {
      'base.physical_plausibility': ['mass_positive'],
      'format.urdf': ['urdf_robot_root'],
    },
    'en',
  )

  assert.match(description, /Physical Plausibility/)
  assert.match(description, /base\.physical_plausibility/)
  assert.match(description, /layer: base/)
  assert.match(description, /mass_positive/)
  assert.match(description, /URDF Source Format/)
  assert.match(description, /urdf_robot_root/)
  assert.doesNotMatch(description, /Legacy:/)
  assert.doesNotMatch(description, /category/i)
  assert.doesNotMatch(description, /physical\.mass_inertia_basic/)
})

test('buildInspectionCriteriaDescription emits localized profile-only criteria in chinese', () => {
  const description = buildInspectionCriteriaDescription(
    {
      'base.physical_plausibility': ['mass_positive'],
    },
    'zh',
  )

  assert.match(description, /通用物理合理性检查/)
  assert.match(description, /base\.physical_plausibility/)
  assert.match(description, /层级：base/)
  assert.match(description, /质量有效性/)
  assert.doesNotMatch(description, /旧字段/)
  assert.doesNotMatch(description, /physical\.mass_inertia_basic/)
})

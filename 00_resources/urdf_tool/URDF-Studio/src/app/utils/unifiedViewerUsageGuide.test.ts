import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveUnifiedViewerUsageGuideVisibility } from './unifiedViewerUsageGuide.ts';

test('resolveUnifiedViewerUsageGuideVisibility honors an explicit override', () => {
  assert.equal(resolveUnifiedViewerUsageGuideVisibility(true, false), false);
  assert.equal(resolveUnifiedViewerUsageGuideVisibility(false, true), true);
});

test('resolveUnifiedViewerUsageGuideVisibility falls back to the stored preference', () => {
  assert.equal(resolveUnifiedViewerUsageGuideVisibility(true, undefined), true);
  assert.equal(resolveUnifiedViewerUsageGuideVisibility(false, undefined), false);
});

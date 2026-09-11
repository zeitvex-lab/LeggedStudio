import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getSourceCodeAutoApplyDebounceMs,
  getUrdfValidationDebounceMs,
} from './editorPerformance.ts';

test('keeps small URDF documents responsive with a short validation debounce', () => {
  assert.equal(getUrdfValidationDebounceMs(512), 120);
});

test('backs off validation a bit for medium and large URDF documents', () => {
  assert.equal(getUrdfValidationDebounceMs(8_000), 180);
  assert.equal(getUrdfValidationDebounceMs(30_000), 320);
});

test('spaces out auto-apply slightly longer than validation to avoid interrupting edits', () => {
  assert.equal(getSourceCodeAutoApplyDebounceMs(512), 500);
  assert.equal(getSourceCodeAutoApplyDebounceMs(8_000), 700);
  assert.equal(getSourceCodeAutoApplyDebounceMs(30_000), 900);
});

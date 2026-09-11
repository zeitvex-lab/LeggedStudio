import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveAppModeAfterRobotContentChange } from './contentChangeAppMode.ts';

test('resolveAppModeAfterRobotContentChange preserves the single editor mode', () => {
  assert.equal(resolveAppModeAfterRobotContentChange('editor'), 'editor');
});

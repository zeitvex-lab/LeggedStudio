import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveUnifiedViewerSceneMode } from './unifiedViewerSceneMode.ts';

test('resolveUnifiedViewerSceneMode keeps the viewer runtime pinned to editor mode', () => {
  assert.equal(resolveUnifiedViewerSceneMode('editor'), 'editor');
});

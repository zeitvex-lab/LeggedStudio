import assert from 'node:assert/strict';
import test from 'node:test';

import { clearIkDragHelperSelection } from './ikDragSession.ts';

test('clearIkDragHelperSelection strips the helper kind while keeping the clicked link selected', () => {
  assert.deepEqual(
    clearIkDragHelperSelection({
      type: 'link',
      id: 'forearm_link',
      helperKind: 'ik-handle',
    }),
    { type: 'link', id: 'forearm_link' },
  );
});

test('clearIkDragHelperSelection leaves unrelated selections untouched', () => {
  assert.equal(
    clearIkDragHelperSelection({
      type: 'link',
      id: 'forearm_link',
      helperKind: 'origin-axes',
    }),
    null,
  );
});

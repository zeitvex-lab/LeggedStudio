import assert from 'node:assert/strict';
import test from 'node:test';

import { createDefaultWorkspace } from '@/core/robot';
import { useWorkspaceStore } from '@/store/workspaceStore';

import { createSemanticWorkspaceSelector } from './useAppLayoutStoreSlices';

test('semantic workspace selector ignores pure joint-motion revisions', () => {
  const base = useWorkspaceStore.getState();
  const initialWorkspace = createDefaultWorkspace('initial');
  const motionWorkspace = structuredClone(initialWorkspace);
  const changedWorkspace = createDefaultWorkspace('semantic-change');
  const select = createSemanticWorkspaceSelector();

  const initial = select({
    ...base,
    workspace: initialWorkspace,
    revision: 4,
    jointMotionRevision: 1,
  });
  const afterMotion = select({
    ...base,
    workspace: motionWorkspace,
    revision: 5,
    jointMotionRevision: 2,
  });
  const afterSemanticChange = select({
    ...base,
    workspace: changedWorkspace,
    revision: 6,
    jointMotionRevision: 2,
  });

  assert.equal(initial, initialWorkspace);
  assert.equal(afterMotion, initialWorkspace);
  assert.equal(afterSemanticChange, changedWorkspace);
});

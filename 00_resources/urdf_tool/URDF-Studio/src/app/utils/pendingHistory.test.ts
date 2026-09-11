import assert from 'node:assert/strict';
import test from 'node:test';

import {
  beginCoordinatedWorkspaceTransaction,
  flushPendingHistory,
  registerPendingHistoryFlusher,
} from './pendingHistory.ts';
import { createDefaultWorkspace } from '@/core/robot';
import { useWorkspaceStore } from '@/store/workspaceStore';

test('pending history exposes one current flusher and stale cleanup cannot clear it', () => {
  const calls: string[] = [];
  const unregisterFirst = registerPendingHistoryFlusher(() => calls.push('first'));
  const unregisterSecond = registerPendingHistoryFlusher(() => calls.push('second'));

  unregisterFirst();
  flushPendingHistory();
  assert.deepEqual(calls, ['second']);

  unregisterSecond();
  flushPendingHistory();
  assert.deepEqual(calls, ['second']);
});

test('coordinated transactions flush property history and reject an exclusive owner', () => {
  const store = useWorkspaceStore.getState();
  if (store.transaction) store.cancelWorkspaceTransaction(store.transaction.id);
  store.replaceWorkspace(createDefaultWorkspace('pending-history'), { resetHistory: true });
  useWorkspaceStore.setState({ history: { past: [], future: [], activity: [] } });

  const pendingId = store.beginWorkspaceTransaction('Pending property edit');
  store.renameWorkspace('edited before discrete action', { operationId: pendingId });
  const unregister = registerPendingHistoryFlusher(() => {
    useWorkspaceStore.getState().commitWorkspaceTransaction(pendingId);
  });
  const discreteId = beginCoordinatedWorkspaceTransaction('Discrete action');
  unregister();

  assert.equal(useWorkspaceStore.getState().transaction?.id, discreteId);
  assert.equal(useWorkspaceStore.getState().history.past.length, 1);
  assert.equal(useWorkspaceStore.getState().workspace.name, 'edited before discrete action');
  useWorkspaceStore.getState().commitWorkspaceTransaction(discreteId);

  const exclusiveId = useWorkspaceStore.getState().beginWorkspaceTransaction(
    'USD hydration',
    { exclusive: true },
  );
  assert.throws(
    () => beginCoordinatedWorkspaceTransaction('Asset mutation'),
    /busy with an exclusive operation/i,
  );
  assert.equal(useWorkspaceStore.getState().transaction?.id, exclusiveId);
  useWorkspaceStore.getState().cancelWorkspaceTransaction(exclusiveId);
});

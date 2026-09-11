import { createStableJsonSnapshot } from '@/core/robot';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { AssemblyState, WorkspaceHistory } from '@/types';

import { flushPendingHistory } from '../../utils/pendingHistory';

export interface ProjectExportPersistenceSnapshot {
  workspace: AssemblyState;
  workspaceHistory: WorkspaceHistory;
  revision: number;
  persistenceToken: string;
}

function createPersistenceToken(
  workspace: AssemblyState,
  workspaceHistory: WorkspaceHistory,
): string {
  return createStableJsonSnapshot({ workspace, workspaceHistory });
}

/**
 * Commit every pending persistent workspace edit, then clone the exact state
 * that will be written to the project archive.
 */
export function captureProjectExportPersistenceSnapshot(): ProjectExportPersistenceSnapshot {
  flushPendingHistory();

  let store = useWorkspaceStore.getState();
  const transaction = store.transaction;
  if (transaction?.exclusive) {
    throw new Error('Cannot export a project while an exclusive workspace operation is active.');
  }
  if (transaction) {
    store.flushPendingJointMotion({ operationId: transaction.id });
    if (!store.commitWorkspaceTransaction(transaction.id)) {
      throw new Error('Failed to commit the pending workspace edit before project export.');
    }
  } else {
    store.flushPendingJointMotion();
  }

  store = useWorkspaceStore.getState();
  if (store.transaction) {
    throw new Error('Cannot capture a project while a workspace edit is still pending.');
  }

  const workspace = structuredClone(store.workspace);
  const workspaceHistory = structuredClone(store.history);
  return {
    workspace,
    workspaceHistory,
    revision: store.revision,
    persistenceToken: createPersistenceToken(workspace, workspaceHistory),
  };
}

/** Only the exact state archived at capture time may become the saved baseline. */
export function isProjectExportPersistenceSnapshotCurrent(
  capture: ProjectExportPersistenceSnapshot,
): boolean {
  const store = useWorkspaceStore.getState();
  return (
    store.transaction === null
    && store.revision === capture.revision
    && createPersistenceToken(store.workspace, store.history) === capture.persistenceToken
  );
}

import {
  type BeginWorkspaceTransactionOptions,
  useWorkspaceStore,
} from '@/store/workspaceStore';

type PendingHistoryFlusher = (() => void) | null;

let pendingHistoryFlusher: PendingHistoryFlusher = null;

export function registerPendingHistoryFlusher(flusher: PendingHistoryFlusher) {
  pendingHistoryFlusher = flusher;
  return () => {
    if (pendingHistoryFlusher === flusher) {
      pendingHistoryFlusher = null;
    }
  };
}

export function flushPendingHistory() {
  pendingHistoryFlusher?.();
}

/**
 * Start a discrete workspace operation after the property editor has finished
 * its debounced transaction. Cross-store workflows must acquire this token
 * before mutating assets so an exclusive workspace operation cannot leave the
 * two stores partially updated.
 */
export function beginCoordinatedWorkspaceTransaction(
  label: string,
  options: BeginWorkspaceTransactionOptions = {},
): string {
  flushPendingHistory();
  const store = useWorkspaceStore.getState();
  if (store.transaction) {
    throw new Error(
      store.transaction.exclusive
        ? 'Workspace is busy with an exclusive operation.'
        : `Workspace transaction "${store.transaction.id}" is already active.`,
    );
  }
  return store.beginWorkspaceTransaction(label, options);
}

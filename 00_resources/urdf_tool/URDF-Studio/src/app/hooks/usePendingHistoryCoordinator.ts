import { useCallback, useEffect, useRef } from 'react';

import { registerPendingHistoryFlusher } from '@/app/utils/pendingHistory';
import { useWorkspaceStore } from '@/store/workspaceStore';

const PROPERTY_HISTORY_COMMIT_DELAY_MS = 220;

interface PendingWorkspaceHistoryEntry {
  key: string;
  operationId: string;
  timeoutId: ReturnType<typeof setTimeout> | null;
}

/**
 * Owns the single property-edit transaction used by workspace mutations.
 * Every write receives the transaction token; no robot/assembly snapshots or
 * renderer-mode scope are involved.
 */
export function usePendingHistoryCoordinator() {
  const pendingRef = useRef<PendingWorkspaceHistoryEntry | null>(null);

  const clearTimer = useCallback((pending: PendingWorkspaceHistoryEntry | null) => {
    if (pending?.timeoutId === null || pending?.timeoutId === undefined) {
      return;
    }
    clearTimeout(pending.timeoutId);
    pending.timeoutId = null;
  }, []);

  const commitPendingHistory = useCallback(
    (expectedKey?: string): boolean => {
      const pending = pendingRef.current;
      if (!pending || (expectedKey !== undefined && pending.key !== expectedKey)) {
        return false;
      }

      clearTimer(pending);
      pendingRef.current = null;
      const store = useWorkspaceStore.getState();
      store.flushPendingJointMotion({ operationId: pending.operationId });
      return store.commitWorkspaceTransaction(pending.operationId);
    },
    [clearTimer],
  );

  const cancelPendingHistory = useCallback(
    (expectedKey?: string): boolean => {
      const pending = pendingRef.current;
      if (!pending || (expectedKey !== undefined && pending.key !== expectedKey)) {
        return false;
      }

      clearTimer(pending);
      pendingRef.current = null;
      return useWorkspaceStore
        .getState()
        .cancelWorkspaceTransaction(pending.operationId);
    },
    [clearTimer],
  );

  const ensurePendingHistory = useCallback(
    (key: string, label: string): string | null => {
      const pending = pendingRef.current;
      if (pending?.key === key) {
        clearTimer(pending);
        return pending.operationId;
      }

      commitPendingHistory();
      const store = useWorkspaceStore.getState();
      if (store.transaction) {
        return null;
      }

      const operationId = store.beginWorkspaceTransaction(label);
      pendingRef.current = { key, operationId, timeoutId: null };
      return operationId;
    },
    [clearTimer, commitPendingHistory],
  );

  const schedulePendingHistoryCommit = useCallback(
    (key: string, delayMs = PROPERTY_HISTORY_COMMIT_DELAY_MS): void => {
      const pending = pendingRef.current;
      if (!pending || pending.key !== key) {
        return;
      }

      clearTimer(pending);
      pending.timeoutId = setTimeout(() => {
        commitPendingHistory(key);
      }, delayMs);
    },
    [clearTimer, commitPendingHistory],
  );

  useEffect(() => {
    const unregister = registerPendingHistoryFlusher(commitPendingHistory);
    return () => {
      commitPendingHistory();
      unregister();
    };
  }, [commitPendingHistory]);

  return {
    cancelPendingHistory,
    commitPendingHistory,
    ensurePendingHistory,
    schedulePendingHistoryCommit,
  };
}

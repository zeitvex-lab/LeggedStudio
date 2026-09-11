import { useMemo } from 'react';

import { useWorkspaceStore } from '@/store/workspaceStore';
import { flushPendingHistory } from '../utils/pendingHistory';

export function useActiveHistory() {
  const undoWorkspace = useWorkspaceStore((state) => state.undo);
  const redoWorkspace = useWorkspaceStore((state) => state.redo);
  const canUndo = useWorkspaceStore((state) => state.canUndo());
  const canRedo = useWorkspaceStore((state) => state.canRedo());

  return useMemo(
    () => ({
      undo: () => {
        flushPendingHistory();
        undoWorkspace();
      },
      redo: () => {
        flushPendingHistory();
        redoWorkspace();
      },
      canUndo,
      canRedo,
    }),
    [canRedo, canUndo, redoWorkspace, undoWorkspace],
  );
}

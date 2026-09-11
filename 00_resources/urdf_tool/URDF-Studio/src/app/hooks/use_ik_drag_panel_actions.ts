import { useCallback, useState } from 'react';
import type { WorkspaceSelection } from '@/types';
import type { ViewOptions } from '@/store/uiStore';
import { isIkDragToolEnabled } from '@/shared/utils/ikDragFeatureGate';

interface UseIkDragPanelActionsParams {
  selection: WorkspaceSelection;
  setSelection: (selection: WorkspaceSelection) => void;
  setViewOption: <K extends keyof ViewOptions>(key: K, value: ViewOptions[K]) => void;
}

export function useIkDragPanelActions({
  selection,
  setSelection,
  setViewOption,
}: UseIkDragPanelActionsParams) {
  const [ikDragActive, setIkDragActive] = useState(false);
  const [isIkToolPanelOpen, setIsIkToolPanelOpen] = useState(false);

  const setIkDragActiveState = useCallback(
    (active: boolean) => {
      setIkDragActive(active);

      if (active) {
        setViewOption('showIkHandles', true);
        return;
      }

      setViewOption('showIkHandles', false);
      setIsIkToolPanelOpen(false);
      if (selection?.helperKind === 'ik-handle') {
        const { helperKind: _helperKind, ...clearedSelection } = selection;
        setSelection(clearedSelection);
      }
    },
    [selection, setSelection, setViewOption],
  );

  const handleOpenIkTool = useCallback(() => {
    if (!isIkDragToolEnabled()) {
      setIkDragActiveState(false);
      return;
    }

    setIkDragActiveState(true);
    setIsIkToolPanelOpen(true);
  }, [setIkDragActiveState]);

  const handleIkDragActiveChange = useCallback(
    (active: boolean) => {
      setIkDragActiveState(active);
    },
    [setIkDragActiveState],
  );

  return {
    ikDragActive,
    isIkToolPanelOpen,
    handleIkDragActiveChange,
    handleOpenIkTool,
  };
}

import { useCallback, useEffect, useState } from 'react';

import { registerUnsavedChangesBaselineMarker } from '@/app/utils/unsavedChangesBaseline';
import {
  isRegressionBeforeUnloadPromptSuppressed,
  subscribeRegressionBeforeUnloadPromptSuppression,
} from '@/shared/debug/regressionPromptSuppression';
import { createStableJsonSnapshot } from '@/shared/utils/robot/semanticSnapshot';
import { useWorkspaceStore } from '@/store/workspaceStore';

function getCurrentWorkspaceSnapshot(): string {
  return createStableJsonSnapshot(useWorkspaceStore.getState().workspace);
}

export function useUnsavedChangesPrompt() {
  const currentSnapshot = useWorkspaceStore((state) =>
    createStableJsonSnapshot(state.workspace),
  );
  const [baseline, setBaseline] = useState(currentSnapshot);
  const [beforeUnloadPromptSuppressed, setBeforeUnloadPromptSuppressed] = useState(() =>
    isRegressionBeforeUnloadPromptSuppressed(),
  );

  const markCurrentStateSaved = useCallback(() => {
    setBaseline(getCurrentWorkspaceSnapshot());
  }, []);
  const hasUnsavedChanges = currentSnapshot !== baseline;

  useEffect(() => {
    registerUnsavedChangesBaselineMarker(markCurrentStateSaved);
    return () => registerUnsavedChangesBaselineMarker(null);
  }, [markCurrentStateSaved]);

  useEffect(() =>
    subscribeRegressionBeforeUnloadPromptSuppression(
      setBeforeUnloadPromptSuppressed,
    ), []);

  useEffect(() => {
    if (typeof window === 'undefined' || !hasUnsavedChanges || beforeUnloadPromptSuppressed) {
      return undefined;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [beforeUnloadPromptSuppressed, hasUnsavedChanges]);

  return { hasUnsavedChanges, markCurrentStateSaved };
}

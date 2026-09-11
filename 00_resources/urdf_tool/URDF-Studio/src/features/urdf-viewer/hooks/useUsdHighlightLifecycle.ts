import { useEffect } from 'react';

export function useUsdHighlightLifecycle(
  syncUsdHighlights: () => void,
  revertUsdHighlights: () => void,
): void {
  useEffect(() => {
    syncUsdHighlights();
  }, [syncUsdHighlights]);

  useEffect(() => {
    return () => {
      revertUsdHighlights();
    };
  }, [revertUsdHighlights]);
}

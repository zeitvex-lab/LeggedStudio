import type { UsdOffscreenViewerWorkerResponse } from '@/features/editor/usd_hydration';
import type { ViewerDocumentLoadEvent } from '@/features/editor';
import { recordUsdStageLoadDebug } from '@/shared/debug/usdStageLoadDebug';

interface HandleUsdHydrationWorkerEventOptions {
  commitHydrationLoadEvent?: (event: ViewerDocumentLoadEvent) => void;
}

export function handleUsdHydrationWorkerEvent(
  event: UsdOffscreenViewerWorkerResponse,
  options: HandleUsdHydrationWorkerEventOptions = {},
): void {
  if (event.type === 'document-load') {
    options.commitHydrationLoadEvent?.(event.event);
    return;
  }

  if (event.type === 'load-debug') {
    recordUsdStageLoadDebug(event.entry);
  }
}

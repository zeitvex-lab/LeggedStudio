import type { ViewerDocumentLoadEvent } from '../types';

export function normalizeUsdBootstrapDocumentLoadEvent(
  event: ViewerDocumentLoadEvent,
  options: {
    useUsdOffscreenBootstrap: boolean;
  },
): ViewerDocumentLoadEvent {
  if (!options.useUsdOffscreenBootstrap || event.status !== 'ready') {
    return event;
  }

  return {
    status: 'loading',
    phase: 'finalizing-scene',
    message: null,
    progressMode: 'indeterminate',
    progressPercent: null,
    loadedCount: null,
    totalCount: null,
    error: null,
  };
}

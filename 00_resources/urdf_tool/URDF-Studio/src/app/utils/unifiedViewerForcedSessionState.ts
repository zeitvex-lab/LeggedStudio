import type { ToolMode } from '@/features/editor';

interface ResolveUnifiedViewerForcedSessionStateArgs {
  forcedViewerSession: boolean;
  pendingViewerToolMode: ToolMode | null;
  viewerToolMode: ToolMode;
}

export function resolveUnifiedViewerForcedSessionState({
  forcedViewerSession,
  pendingViewerToolMode,
  viewerToolMode,
}: ResolveUnifiedViewerForcedSessionStateArgs): boolean {
  if (pendingViewerToolMode === 'measure') {
    return true;
  }

  if (!forcedViewerSession) {
    return false;
  }

  if (viewerToolMode === 'measure') {
    return true;
  }

  return false;
}

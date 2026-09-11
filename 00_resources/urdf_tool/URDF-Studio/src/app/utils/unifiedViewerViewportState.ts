import type { DocumentLoadLifecycleState } from '@/store/assetsStore';
import type { UnifiedViewerMountState } from './unifiedViewerMountState';

interface ResolveUnifiedViewerViewportStateArgs {
  isViewerMode: boolean;
  mountState: UnifiedViewerMountState;
  activeViewportFileName: string | null;
  viewerReloadKey: number;
  documentLoadState: DocumentLoadLifecycleState;
}

export interface UnifiedViewerViewportState {
  activeViewerDocumentStillLoading: boolean;
  viewerLoadScopeKey: string;
  viewerVisible: boolean;
  shouldRenderViewerScene: boolean;
  useViewerCanvasPresentation: boolean;
}

function isViewerDocumentLoadingForScope(
  activeFileName: string | null,
  documentLoadState: DocumentLoadLifecycleState,
): boolean {
  if (!(documentLoadState.status === 'loading' || documentLoadState.status === 'hydrating')) {
    return false;
  }

  if (!activeFileName || !documentLoadState.fileName) {
    return true;
  }

  if (documentLoadState.fileName === activeFileName) {
    return true;
  }

  const activeBaseName = activeFileName.replace(/\\/g, '/').split('/').pop();
  const loadingBaseName = documentLoadState.fileName.replace(/\\/g, '/').split('/').pop();
  return Boolean(activeBaseName && loadingBaseName && activeBaseName === loadingBaseName);
}

export function resolveUnifiedViewerViewportState({
  isViewerMode,
  mountState,
  activeViewportFileName,
  viewerReloadKey,
  documentLoadState,
}: ResolveUnifiedViewerViewportStateArgs): UnifiedViewerViewportState {
  const activeViewerDocumentStillLoading =
    isViewerMode && isViewerDocumentLoadingForScope(activeViewportFileName, documentLoadState);
  const viewerLoadScopeKey = activeViewportFileName
    ? `${activeViewportFileName}:${viewerReloadKey}`
    : `viewer-reload:${viewerReloadKey}`;
  const viewerVisible = isViewerMode;
  const shouldRenderViewerScene = mountState.viewerMounted || viewerVisible;
  const useViewerCanvasPresentation = viewerVisible;

  return {
    activeViewerDocumentStillLoading,
    viewerLoadScopeKey,
    viewerVisible,
    shouldRenderViewerScene,
    useViewerCanvasPresentation,
  };
}

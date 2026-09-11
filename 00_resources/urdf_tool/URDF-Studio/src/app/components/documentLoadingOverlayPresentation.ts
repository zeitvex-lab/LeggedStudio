import { VIEWER_CORNER_OVERLAY_CLASS_NAME } from '@/shared/components/3d/scene';

export interface DocumentLoadingOverlayLikeState {
  status: 'idle' | 'loading' | 'hydrating' | 'ready' | 'error';
  format?: string | null;
}

export interface DocumentLoadingOverlayPresentation {
  blocksViewport: boolean;
  overlayClassName: string;
  hudWrapperClassName?: string;
}

export function shouldBlockDocumentViewport(state: DocumentLoadingOverlayLikeState): boolean {
  void state;
  return false;
}

export function resolveDocumentLoadingOverlayPresentation(
  state: DocumentLoadingOverlayLikeState,
): DocumentLoadingOverlayPresentation {
  const blocksViewport = shouldBlockDocumentViewport(state);

  return {
    blocksViewport,
    // Keep the workspace canvas visible while documents stream in so the user
    // still sees the horizon, grid, and existing empty-stage context instead of
    // a near-opaque white curtain.
    overlayClassName: VIEWER_CORNER_OVERLAY_CLASS_NAME,
    hudWrapperClassName: undefined,
  };
}

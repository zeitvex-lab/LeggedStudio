export interface UnifiedViewerOptionsVisibilitySnapshot {
  viewer: boolean;
}

interface CaptureUnifiedViewerOptionsVisibilityArgs {
  showViewerOptions: boolean;
}

interface ResolveUnifiedViewerOptionsRestoreArgs {
  wasVisibleAtPointerDown: boolean;
  isVisibleNow: boolean;
  hasRestoreHandler: boolean;
}

export function captureUnifiedViewerOptionsVisibility({
  showViewerOptions,
}: CaptureUnifiedViewerOptionsVisibilityArgs): UnifiedViewerOptionsVisibilitySnapshot {
  return {
    viewer: showViewerOptions,
  };
}

export function shouldRestoreUnifiedViewerOptionsPanel({
  wasVisibleAtPointerDown,
  isVisibleNow,
  hasRestoreHandler,
}: ResolveUnifiedViewerOptionsRestoreArgs): boolean {
  return hasRestoreHandler && wasVisibleAtPointerDown && !isVisibleNow;
}

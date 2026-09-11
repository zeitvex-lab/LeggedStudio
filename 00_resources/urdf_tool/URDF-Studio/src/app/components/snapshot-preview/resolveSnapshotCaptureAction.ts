import type { SnapshotCaptureAction } from '@/shared/components/3d';

interface ResolveSnapshotCaptureActionOptions {
  liveCaptureAction: SnapshotCaptureAction | null;
  frozenPreviewCaptureAction: SnapshotCaptureAction | null;
  preferFrozenPreviewCapture: boolean;
}

export type ResolvedSnapshotCaptureSource = 'live' | 'preview';

export interface ResolvedSnapshotCaptureAction {
  action: SnapshotCaptureAction;
  source: ResolvedSnapshotCaptureSource;
}

export function resolveSnapshotCaptureAction({
  liveCaptureAction,
  frozenPreviewCaptureAction,
  preferFrozenPreviewCapture,
}: ResolveSnapshotCaptureActionOptions): ResolvedSnapshotCaptureAction | null {
  if (preferFrozenPreviewCapture) {
    return frozenPreviewCaptureAction
      ? { action: frozenPreviewCaptureAction, source: 'preview' }
      : null;
  }

  return liveCaptureAction ? { action: liveCaptureAction, source: 'live' } : null;
}

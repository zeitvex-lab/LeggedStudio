import type { SnapshotPreviewAction } from '@/shared/components/3d';

export function toSnapshotPreviewActionState(nextAction: SnapshotPreviewAction | null) {
  return (_previousAction: SnapshotPreviewAction | null) => nextAction;
}

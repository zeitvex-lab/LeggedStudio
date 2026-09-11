import assert from 'node:assert/strict';
import test from 'node:test';

import type { SnapshotPreviewAction } from '@/shared/components/3d';

import { toSnapshotPreviewActionState } from './previewActionState';

test('toSnapshotPreviewActionState preserves callback identity without invoking it', async () => {
  let callCount = 0;
  const action: SnapshotPreviewAction = async () => {
    callCount += 1;
    return {
      blob: new Blob(['preview']),
      width: 640,
      height: 360,
      options: {
        longEdgePx: 1280,
        imageFormat: 'png',
        imageQuality: 96,
        detailLevel: 'high',
        environmentPreset: 'city',
        shadowStyle: 'balanced',
        groundStyle: 'shadow',
        dofMode: 'off',
        backgroundStyle: 'studio',
        hideGrid: true,
        aspectRatioPreset: 'viewport',
        pngOptimizeLevel: 2,
      },
    };
  };

  const updater = toSnapshotPreviewActionState(action);
  const storedAction = updater(null);

  assert.equal(callCount, 0, 'wrapping the callback should not invoke it eagerly');
  assert.equal(storedAction, action, 'the updater should preserve the original callback identity');
});

test('toSnapshotPreviewActionState can clear the stored callback', () => {
  const updater = toSnapshotPreviewActionState(null);

  assert.equal(
    updater(() => Promise.reject(new Error('unused'))),
    null,
  );
});

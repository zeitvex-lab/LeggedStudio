import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveSnapshotPreviewCaptureOptions } from './snapshotPreviewConfig';

test('resolveSnapshotPreviewCaptureOptions keeps the export look but caps preview budget', () => {
  const options = resolveSnapshotPreviewCaptureOptions({
    longEdgePx: 7680,
    imageFormat: 'webp',
    imageQuality: 80,
    detailLevel: 'ultra',
    environmentPreset: 'contrast',
    shadowStyle: 'crisp',
    groundStyle: 'reflective',
    dofMode: 'hero',
    backgroundStyle: 'dark',
    hideGrid: false,
  });

  assert.equal(options.longEdgePx, 800);
  assert.equal(options.detailLevel, 'high');
  assert.equal(options.imageFormat, 'webp');
  assert.equal(options.imageQuality, 80);
  assert.equal(options.environmentPreset, 'contrast');
  assert.equal(options.shadowStyle, 'crisp');
  assert.equal(options.groundStyle, 'reflective');
  assert.equal(options.dofMode, 'off');
  assert.equal(options.backgroundStyle, 'dark');
  assert.equal(options.hideGrid, false);
});

test('resolveSnapshotPreviewCaptureOptions keeps transparent alpha-safe previews intact', () => {
  const options = resolveSnapshotPreviewCaptureOptions({
    imageFormat: 'png',
    backgroundStyle: 'transparent',
    dofMode: 'hero',
  });

  assert.equal(options.longEdgePx, 800);
  assert.equal(options.backgroundStyle, 'transparent');
  assert.equal(options.dofMode, 'off');
});

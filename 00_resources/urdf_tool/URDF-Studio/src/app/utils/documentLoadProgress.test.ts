import assert from 'node:assert/strict';
import test from 'node:test';

import {
  mapRobotImportProgressToDocumentLoadPercent,
  mapViewerDocumentLoadEventToDocumentLoadPercent,
  resolveDocumentLoadingOverlayTargetFileName,
} from './documentLoadProgress.ts';

test('mapRobotImportProgressToDocumentLoadPercent maps URDF worker progress into the global bootstrap range', () => {
  assert.equal(
    mapRobotImportProgressToDocumentLoadPercent('urdf', {
      progressPercent: 50,
      message: 'Parsing URDF',
    }),
    20,
  );
});

test('mapViewerDocumentLoadEventToDocumentLoadPercent maps USD viewer progress into the post-bootstrap range', () => {
  assert.equal(
    mapViewerDocumentLoadEventToDocumentLoadPercent('usd', {
      status: 'loading',
      phase: 'checking-path',
      progressMode: 'percent',
      progressPercent: 50,
      loadedCount: null,
      totalCount: null,
    }),
    12,
  );
});

test('mapViewerDocumentLoadEventToDocumentLoadPercent keeps early USD dependency preload progress below the first-quarter jump', () => {
  const mappedProgress = mapViewerDocumentLoadEventToDocumentLoadPercent('usd', {
    status: 'loading',
    phase: 'preloading-dependencies',
    progressMode: 'percent',
    progressPercent: 34,
    loadedCount: null,
    totalCount: null,
  });

  assert.ok(mappedProgress < 20);
  assert.ok(mappedProgress > 18);
});

test('resolveDocumentLoadingOverlayTargetFileName prefers the actively loading file over preview or selection state', () => {
  assert.equal(
    resolveDocumentLoadingOverlayTargetFileName({
      previewFileName: 'robots/preview.urdf',
      selectedFileName: 'robots/selected.urdf',
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/loading.urdf',
      },
    }),
    'robots/loading.urdf',
  );
});

test('resolveDocumentLoadingOverlayTargetFileName suppresses stale document loading while workspace overlay owns progress', () => {
  assert.equal(
    resolveDocumentLoadingOverlayTargetFileName({
      previewFileName: null,
      selectedFileName: 'robots/selected.urdf',
      suppressDocumentLoadingOverlay: true,
      documentLoadState: {
        status: 'loading',
        fileName: 'robots/selected.urdf',
      },
    }),
    null,
  );
});

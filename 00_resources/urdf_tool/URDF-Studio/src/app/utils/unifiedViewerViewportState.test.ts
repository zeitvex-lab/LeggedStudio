import test from 'node:test';
import assert from 'node:assert/strict';

import type { DocumentLoadState } from '@/store/assetsStore';
import { resolveUnifiedViewerViewportState } from './unifiedViewerViewportState';

function createDocumentLoadState(overrides: Partial<DocumentLoadState> = {}): DocumentLoadState {
  return {
    status: 'idle',
    fileName: null,
    format: null,
    error: null,
    ...overrides,
  };
}

test('resolveUnifiedViewerViewportState follows direct viewer ownership when the active file is loading', () => {
  const state = resolveUnifiedViewerViewportState({
    isViewerMode: true,
    mountState: {
      viewerMounted: true,
    },
    activeViewportFileName: 'robots/go2/urdf/go2.urdf',
    viewerReloadKey: 4,
    documentLoadState: createDocumentLoadState({
      status: 'loading',
      fileName: 'robots/go2/urdf/go2.urdf',
      format: 'urdf',
    }),
  });

  assert.equal(state.activeViewerDocumentStillLoading, true);
  assert.equal(state.viewerLoadScopeKey, 'robots/go2/urdf/go2.urdf:4');
  assert.equal(state.viewerVisible, true);
  assert.equal(state.shouldRenderViewerScene, true);
  assert.equal(state.useViewerCanvasPresentation, true);
});

test('resolveUnifiedViewerViewportState stays on the viewer while the same active document is still reloading', () => {
  const state = resolveUnifiedViewerViewportState({
    isViewerMode: true,
    mountState: {
      viewerMounted: true,
    },
    activeViewportFileName: 'robots/go2/urdf/go2.urdf',
    viewerReloadKey: 1,
    documentLoadState: createDocumentLoadState({
      status: 'hydrating',
      fileName: 'go2.urdf',
      format: 'usd',
    }),
  });

  assert.equal(state.activeViewerDocumentStillLoading, true);
  assert.equal(state.viewerLoadScopeKey, 'robots/go2/urdf/go2.urdf:1');
  assert.equal(state.viewerVisible, true);
  assert.equal(state.shouldRenderViewerScene, true);
  assert.equal(state.useViewerCanvasPresentation, true);
});

test('resolveUnifiedViewerViewportState hides viewer presentation outside an active viewer session', () => {
  const state = resolveUnifiedViewerViewportState({
    isViewerMode: false,
    mountState: {
      viewerMounted: false,
    },
    activeViewportFileName: null,
    viewerReloadKey: 2,
    documentLoadState: createDocumentLoadState(),
  });

  assert.equal(state.activeViewerDocumentStillLoading, false);
  assert.equal(state.viewerLoadScopeKey, 'viewer-reload:2');
  assert.equal(state.viewerVisible, false);
  assert.equal(state.shouldRenderViewerScene, false);
  assert.equal(state.useViewerCanvasPresentation, false);
});

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

test('viewer load detection treats basename-equivalent paths as the same scope', () => {
  const state = resolveUnifiedViewerViewportState({
    isViewerMode: true,
    mountState: {
      viewerMounted: true,
    },
    activeViewportFileName: 'anybotics_anymal_c/scene.xml',
    viewerReloadKey: 1,
    documentLoadState: createDocumentLoadState({
      status: 'loading',
      fileName: 'scene.xml',
    }),
  });

  assert.equal(state.activeViewerDocumentStillLoading, true);
});

test('viewer load detection ignores non-loading document states', () => {
  const readyState = resolveUnifiedViewerViewportState({
    isViewerMode: true,
    mountState: {
      viewerMounted: true,
    },
    activeViewportFileName: 'g1_description/g1_29dof.urdf',
    viewerReloadKey: 1,
    documentLoadState: createDocumentLoadState({
      status: 'ready',
      fileName: 'g1_description/g1_29dof.urdf',
      format: 'urdf',
    }),
  });

  const errorState = resolveUnifiedViewerViewportState({
    isViewerMode: true,
    mountState: {
      viewerMounted: true,
    },
    activeViewportFileName: 'g1_description/g1_29dof.urdf',
    viewerReloadKey: 1,
    documentLoadState: createDocumentLoadState({
      status: 'error',
      fileName: 'g1_description/g1_29dof.urdf',
      format: 'urdf',
      error: 'failed',
    }),
  });

  assert.equal(readyState.activeViewerDocumentStillLoading, false);
  assert.equal(errorState.activeViewerDocumentStillLoading, false);
});

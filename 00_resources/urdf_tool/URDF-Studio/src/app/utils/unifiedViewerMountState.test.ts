import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createInitialUnifiedViewerMountState,
  resolveUnifiedViewerMountState,
  resolveUnifiedViewerSessionState,
} from './unifiedViewerMountState.ts';

test('starts with the viewer mounted when appMode is `editor`', () => {
  assert.deepEqual(
    createInitialUnifiedViewerMountState({
      mode: 'editor',
      isPreviewing: false,
    }),
    {
      viewerMounted: true,
    },
  );
});

test('keeps the viewer mounted across repeated editor sessions', () => {
  const initialState = createInitialUnifiedViewerMountState({
    mode: 'editor',
    isPreviewing: false,
  });
  const nextState = resolveUnifiedViewerMountState(initialState, {
    mode: 'editor',
    isPreviewing: false,
  });

  assert.deepEqual(nextState, {
    viewerMounted: true,
  });
});

test('treats standalone file preview as a viewer session for keep-alive purposes', () => {
  const initialState = createInitialUnifiedViewerMountState({
    mode: 'editor',
    isPreviewing: false,
  });

  assert.deepEqual(
    resolveUnifiedViewerMountState(initialState, {
      mode: 'editor',
      isPreviewing: true,
    }),
    {
      viewerMounted: true,
    },
  );
});

test('treats a forced viewer session as viewer mode while appMode stays `editor`', () => {
  assert.deepEqual(
    resolveUnifiedViewerSessionState({
      mode: 'editor',
      forceViewerSession: true,
    }),
    {
      activePreview: undefined,
      isPreviewing: false,
      isViewerMode: true,
      viewerSceneMode: 'editor',
    },
  );
});

test('keeps the viewer mounted when an editor session forces the viewer open', () => {
  const initialState = createInitialUnifiedViewerMountState({
    mode: 'editor',
    isPreviewing: false,
  });

  assert.deepEqual(
    resolveUnifiedViewerMountState(initialState, {
      mode: 'editor',
      isPreviewing: false,
      forceViewerSession: true,
    }),
    {
      viewerMounted: true,
    },
  );
});

test('keeps file preview active while appMode is `editor`', () => {
  const preview = {
    urdfContent: '<robot name="preview" />',
    fileName: 'preview/demo.urdf',
  };

  assert.deepEqual(
    resolveUnifiedViewerSessionState({
      mode: 'editor',
      filePreview: preview,
    }),
    {
      activePreview: preview,
      isPreviewing: true,
      isViewerMode: true,
      viewerSceneMode: 'editor',
    },
  );
});

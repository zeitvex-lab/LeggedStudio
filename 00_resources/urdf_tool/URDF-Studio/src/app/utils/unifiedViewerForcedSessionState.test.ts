import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveUnifiedViewerForcedSessionState } from './unifiedViewerForcedSessionState';

test('resolveUnifiedViewerForcedSessionState starts a forced session for pending measure mode', () => {
  assert.equal(
    resolveUnifiedViewerForcedSessionState({
      forcedViewerSession: false,
      pendingViewerToolMode: 'measure',
      viewerToolMode: 'select',
    }),
    true,
  );
});

test('resolveUnifiedViewerForcedSessionState keeps a forced session while measure remains active', () => {
  assert.equal(
    resolveUnifiedViewerForcedSessionState({
      forcedViewerSession: true,
      pendingViewerToolMode: null,
      viewerToolMode: 'measure',
    }),
    true,
  );
});

test('resolveUnifiedViewerForcedSessionState releases a forced session after measure exits', () => {
  assert.equal(
    resolveUnifiedViewerForcedSessionState({
      forcedViewerSession: true,
      pendingViewerToolMode: null,
      viewerToolMode: 'select',
    }),
    false,
  );
});

test('resolveUnifiedViewerForcedSessionState does not force ordinary viewer tool changes', () => {
  assert.equal(
    resolveUnifiedViewerForcedSessionState({
      forcedViewerSession: false,
      pendingViewerToolMode: 'rotate',
      viewerToolMode: 'rotate',
    }),
    false,
  );
});

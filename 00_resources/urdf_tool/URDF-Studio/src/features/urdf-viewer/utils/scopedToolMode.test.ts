import test from 'node:test';
import assert from 'node:assert/strict';
import {
  createScopedToolModeState,
  resolveDefaultViewerToolMode,
  resolveScopedToolModeState,
} from './scopedToolMode';

test('resolveDefaultViewerToolMode keeps document defaults on select mode', () => {
  assert.equal(resolveDefaultViewerToolMode('usd'), 'select');
  assert.equal(resolveDefaultViewerToolMode('urdf'), 'select');
  assert.equal(resolveDefaultViewerToolMode(null), 'select');
});

test('resolveScopedToolModeState resets to the default mode when the document scope changes', () => {
  const current = {
    scopeKey: 'urdf:file-a',
    explicit: true,
    mode: 'rotate',
  } as const;

  assert.deepEqual(
    resolveScopedToolModeState(current, 'usd:file-b', 'view'),
    createScopedToolModeState('usd:file-b', 'view'),
  );
});

test('resolveScopedToolModeState preserves explicit tool choices within one scope', () => {
  const current = {
    scopeKey: 'usd:file-a',
    explicit: true,
    mode: 'select',
  } as const;

  assert.equal(
    resolveScopedToolModeState(current, 'usd:file-a', 'view'),
    current,
  );
});

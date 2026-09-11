import assert from 'node:assert/strict';
import test from 'node:test';

import type { SnapshotCaptureAction } from '@/shared/components/3d';

import { resolveSnapshotCaptureAction } from './resolveSnapshotCaptureAction';

test('resolveSnapshotCaptureAction prefers the frozen preview capture path when requested', () => {
  const liveCaptureAction: SnapshotCaptureAction = async () => {};
  const frozenPreviewCaptureAction: SnapshotCaptureAction = async () => {};

  const resolvedAction = resolveSnapshotCaptureAction({
    liveCaptureAction,
    frozenPreviewCaptureAction,
    preferFrozenPreviewCapture: true,
  });

  assert.equal(resolvedAction?.action, frozenPreviewCaptureAction);
  assert.equal(resolvedAction?.source, 'preview');
});

test('resolveSnapshotCaptureAction keeps using the live viewer capture path when no frozen preview export is needed', () => {
  const liveCaptureAction: SnapshotCaptureAction = async () => {};
  const frozenPreviewCaptureAction: SnapshotCaptureAction = async () => {};

  const resolvedAction = resolveSnapshotCaptureAction({
    liveCaptureAction,
    frozenPreviewCaptureAction,
    preferFrozenPreviewCapture: false,
  });

  assert.equal(resolvedAction?.action, liveCaptureAction);
  assert.equal(resolvedAction?.source, 'live');
});

test('resolveSnapshotCaptureAction does not fall back to the live viewer while a frozen preview export is pending', () => {
  const liveCaptureAction: SnapshotCaptureAction = async () => {};

  const resolvedAction = resolveSnapshotCaptureAction({
    liveCaptureAction,
    frozenPreviewCaptureAction: null,
    preferFrozenPreviewCapture: true,
  });

  assert.equal(resolvedAction, null);
});

test('resolveSnapshotCaptureAction reports live source when falling back to the viewer', () => {
  const liveCaptureAction: SnapshotCaptureAction = async () => {};

  const resolvedAction = resolveSnapshotCaptureAction({
    liveCaptureAction,
    frozenPreviewCaptureAction: null,
    preferFrozenPreviewCapture: false,
  });

  assert.equal(resolvedAction?.action, liveCaptureAction);
  assert.equal(resolvedAction?.source, 'live');
});

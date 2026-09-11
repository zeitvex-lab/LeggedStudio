import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveDocumentLoadingOverlayPresentation } from './documentLoadingOverlayPresentation.ts';
import { VIEWER_CORNER_OVERLAY_CLASS_NAME } from '@/shared/components/3d/scene';

test('USD loading keeps the lightweight corner HUD presentation', () => {
  const presentation = resolveDocumentLoadingOverlayPresentation({
    status: 'loading',
    format: 'usd',
  });

  assert.equal(presentation.blocksViewport, false);
  assert.equal(
    presentation.overlayClassName,
    VIEWER_CORNER_OVERLAY_CLASS_NAME,
  );
  assert.equal(presentation.hudWrapperClassName, undefined);
});

test('non-USD loading keeps the lightweight corner HUD presentation', () => {
  const presentation = resolveDocumentLoadingOverlayPresentation({
    status: 'loading',
    format: 'urdf',
  });

  assert.equal(presentation.blocksViewport, false);
  assert.equal(
    presentation.overlayClassName,
    VIEWER_CORNER_OVERLAY_CLASS_NAME,
  );
  assert.equal(presentation.hudWrapperClassName, undefined);
});

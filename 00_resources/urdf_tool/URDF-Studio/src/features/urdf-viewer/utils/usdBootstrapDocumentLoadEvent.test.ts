import test from 'node:test';
import assert from 'node:assert/strict';

import type { ViewerDocumentLoadEvent } from '../types';
import { normalizeUsdBootstrapDocumentLoadEvent } from './usdBootstrapDocumentLoadEvent';

test('normalizeUsdBootstrapDocumentLoadEvent keeps non-bootstrap ready events unchanged', () => {
  const event: ViewerDocumentLoadEvent = {
    status: 'ready',
    phase: 'ready',
    progressPercent: 100,
    loadedCount: null,
    totalCount: null,
    message: null,
    error: null,
  };

  assert.deepEqual(
    normalizeUsdBootstrapDocumentLoadEvent(event, {
      useUsdOffscreenBootstrap: false,
    }),
    event,
  );
});

test('normalizeUsdBootstrapDocumentLoadEvent keeps bootstrap progress in finalizing-scene until interactive stage is ready', () => {
  const event: ViewerDocumentLoadEvent = {
    status: 'ready',
    phase: 'ready',
    progressMode: 'percent',
    progressPercent: 100,
    loadedCount: 12,
    totalCount: 12,
    message: 'Offscreen bootstrap ready',
    error: null,
  };

  assert.deepEqual(
    normalizeUsdBootstrapDocumentLoadEvent(event, {
      useUsdOffscreenBootstrap: true,
    }),
    {
      status: 'loading',
      phase: 'finalizing-scene',
      progressMode: 'indeterminate',
      progressPercent: null,
      loadedCount: null,
      totalCount: null,
      message: null,
      error: null,
    },
  );
});

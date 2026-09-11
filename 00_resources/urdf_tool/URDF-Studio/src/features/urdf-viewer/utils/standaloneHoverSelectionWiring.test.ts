import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveStandaloneViewerHoverSelectionWiring } from './standaloneHoverSelectionWiring.ts';

test('standalone URDF viewer keeps hover enabled for non-USD scenes without an external hover prop', () => {
  const state = resolveStandaloneViewerHoverSelectionWiring({
    sourceFormat: 'urdf',
  });

  assert.deepEqual(state, {
    shouldSubscribeToStoreHoveredSelection: false,
    hoverSelectionEnabled: true,
  });
});

test('standalone USD viewer bridges hovered selection from the store when the parent does not provide it', () => {
  const state = resolveStandaloneViewerHoverSelectionWiring({
    sourceFormat: 'usd',
  });

  assert.deepEqual(state, {
    shouldSubscribeToStoreHoveredSelection: true,
    hoverSelectionEnabled: true,
  });
});

test('standalone viewer prefers an explicit hover prop over subscribing to the store', () => {
  const state = resolveStandaloneViewerHoverSelectionWiring({
    hoveredSelection: { type: 'link', id: 'base_link' },
    sourceFormat: 'usd',
  });

  assert.deepEqual(state, {
    shouldSubscribeToStoreHoveredSelection: false,
    hoverSelectionEnabled: true,
  });
});

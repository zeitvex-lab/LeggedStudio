import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { resolveHoverSelectionState } from './hoverSelectionState.ts';

test('resolveHoverSelectionState preserves exact-match geometry metadata', () => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());

  const resolved = resolveHoverSelectionState({
    source: 'exact',
    match: {
      meta: {
        linkId: 'base_link',
        highlightTarget: mesh,
        objectIndex: 2,
      },
      distance: 1.5,
    },
  });

  assert.equal(resolved.linkId, 'base_link');
  assert.equal(resolved.highlightTarget, mesh);
  assert.equal(resolved.objectIndex, 2);
});

test('resolveHoverSelectionState preserves bounds-fallback geometry metadata', () => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());

  const resolved = resolveHoverSelectionState({
    source: 'bounds',
    match: {
      meta: {
        linkId: 'tiny_link',
        highlightTarget: mesh,
        objectIndex: 1,
      },
      distance: 2.4,
      padding: 0.02,
    },
  });

  assert.equal(resolved.linkId, 'tiny_link');
  assert.equal(resolved.highlightTarget, mesh);
  assert.equal(resolved.objectIndex, 1);
});

test('resolveHoverSelectionState resets hover state when no match exists', () => {
  const resolved = resolveHoverSelectionState(null);

  assert.equal(resolved.linkId, null);
  assert.equal(resolved.highlightTarget, null);
  assert.equal(resolved.objectIndex, undefined);
});

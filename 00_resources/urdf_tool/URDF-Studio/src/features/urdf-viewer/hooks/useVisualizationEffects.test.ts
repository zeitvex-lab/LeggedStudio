import test from 'node:test';
import assert from 'node:assert/strict';

import { areHighlightTargetsEquivalent } from './useVisualizationEffects.ts';

test('areHighlightTargetsEquivalent treats a hovered mesh target as equivalent to a broader selection on the same mesh body', () => {
  assert.equal(
    areHighlightTargetsEquivalent(
      {
        id: 'base_link',
        subType: 'visual',
        objectIndex: 0,
        highlightObjectId: 101,
      },
      {
        id: 'base_link',
        subType: 'visual',
        objectIndex: 0,
        highlightObjectId: undefined,
      },
    ),
    true,
  );
});

test('areHighlightTargetsEquivalent still distinguishes different meshes on the same link', () => {
  assert.equal(
    areHighlightTargetsEquivalent(
      {
        id: 'base_link',
        subType: 'visual',
        objectIndex: 0,
        highlightObjectId: 101,
      },
      {
        id: 'base_link',
        subType: 'visual',
        objectIndex: 1,
        highlightObjectId: undefined,
      },
    ),
    false,
  );
});

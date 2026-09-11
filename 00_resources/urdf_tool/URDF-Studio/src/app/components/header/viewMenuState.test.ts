import assert from 'node:assert/strict';
import test from 'node:test';

import { setOptionsPanelVisibility, toggleOptionsPanel, toggleViewPanel } from './viewMenuState.js';

test('toggleViewPanel marks a single panel as visible without changing other fields', () => {
  const next = toggleViewPanel(
    {
      showOptionsPanel: false,
      showJointPanel: false,
      showStructureGraph: false,
    },
    'showJointPanel',
  );

  assert.deepEqual(next, {
    showOptionsPanel: false,
    showJointPanel: true,
    showStructureGraph: false,
  });
});

test('toggleOptionsPanel opens the unified options panel', () => {
  const next = toggleOptionsPanel({
    showOptionsPanel: false,
    showJointPanel: false,
    showStructureGraph: false,
  });

  assert.deepEqual(next, {
    showOptionsPanel: true,
    showJointPanel: false,
    showStructureGraph: false,
  });
});

test('toggleOptionsPanel closes the unified options panel when it is visible', () => {
  const current = {
    showOptionsPanel: true,
    showJointPanel: false,
    showStructureGraph: false,
  };

  assert.deepEqual(toggleOptionsPanel(current), {
    showOptionsPanel: false,
    showJointPanel: false,
    showStructureGraph: false,
  });
});

test('setOptionsPanelVisibility updates the unified options panel without touching other fields', () => {
  const current = {
    showOptionsPanel: false,
    showJointPanel: true,
    showStructureGraph: true,
  };

  assert.deepEqual(setOptionsPanelVisibility(current, false), {
    showOptionsPanel: false,
    showJointPanel: true,
    showStructureGraph: true,
  });
});

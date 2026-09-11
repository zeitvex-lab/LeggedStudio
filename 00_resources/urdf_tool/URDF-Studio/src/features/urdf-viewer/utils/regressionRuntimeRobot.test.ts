import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveRegressionRuntimeRobot } from './regressionRuntimeRobot.ts';

test('resolveRegressionRuntimeRobot falls back to the primary Three runtime robot', () => {
  const primaryRobot = { name: 'three-runtime' };

  assert.equal(
    resolveRegressionRuntimeRobot({
      robot: primaryRobot,
      jointPanelRobot: null,
    }),
    primaryRobot,
  );
});

test('resolveRegressionRuntimeRobot keeps the joint-panel runtime robot when present', () => {
  const primaryRobot = { name: 'three-runtime' };
  const jointPanelRobot = { name: 'stage-runtime' };

  assert.equal(
    resolveRegressionRuntimeRobot({
      robot: primaryRobot,
      jointPanelRobot,
    }),
    jointPanelRobot,
  );
});

test('resolveRegressionRuntimeRobot returns null when no runtime robot is available', () => {
  assert.equal(
    resolveRegressionRuntimeRobot({
      robot: null,
      jointPanelRobot: null,
    }),
    null,
  );
});

test('resolveRegressionRuntimeRobot can suppress primary fallback while a new source is loading', () => {
  const stalePrimaryRobot = { name: 'previous-three-runtime' };

  assert.equal(
    resolveRegressionRuntimeRobot({
      robot: stalePrimaryRobot,
      jointPanelRobot: null,
      includePrimaryRobot: false,
    }),
    null,
  );
});

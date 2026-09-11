import test from 'node:test';
import assert from 'node:assert/strict';

import { shouldWaitForStructuredUrdfRobotState } from './urdfXmlFallbackPolicy';

test('shouldWaitForStructuredUrdfRobotState waits for canonical URDF state on non-preview loads', () => {
  assert.equal(
    shouldWaitForStructuredUrdfRobotState({
      resolvedSourceFormat: 'urdf',
      hasStructuredRobotState: false,
      allowUrdfXmlFallback: false,
    }),
    true,
  );
});

test('shouldWaitForStructuredUrdfRobotState preserves preview/raw-content fallback paths', () => {
  assert.equal(
    shouldWaitForStructuredUrdfRobotState({
      resolvedSourceFormat: 'urdf',
      hasStructuredRobotState: false,
      allowUrdfXmlFallback: true,
    }),
    false,
  );
});

test('shouldWaitForStructuredUrdfRobotState does not block structured or MJCF loads', () => {
  assert.equal(
    shouldWaitForStructuredUrdfRobotState({
      resolvedSourceFormat: 'urdf',
      hasStructuredRobotState: true,
      allowUrdfXmlFallback: false,
    }),
    false,
  );
  assert.equal(
    shouldWaitForStructuredUrdfRobotState({
      resolvedSourceFormat: 'mjcf',
      hasStructuredRobotState: false,
      allowUrdfXmlFallback: false,
    }),
    false,
  );
  assert.equal(
    shouldWaitForStructuredUrdfRobotState({
      resolvedSourceFormat: 'xacro',
      hasStructuredRobotState: false,
      allowUrdfXmlFallback: false,
    }),
    false,
  );
});

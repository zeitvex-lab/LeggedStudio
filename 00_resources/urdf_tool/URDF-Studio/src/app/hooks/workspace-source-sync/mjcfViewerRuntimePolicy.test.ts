import test from 'node:test';
import assert from 'node:assert/strict';

import {
  USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF,
  resolveStandaloneViewerContent,
  resolveStandaloneViewerSourceFormat,
} from './mjcfViewerRuntimePolicy';

test('resolveStandaloneViewerSourceFormat keeps standalone MJCF files on the MJCF runtime path', () => {
  assert.equal(resolveStandaloneViewerSourceFormat('mjcf'), 'mjcf');
});

test('resolveStandaloneViewerSourceFormat routes hydrated USD through RobotState URDF runtime', () => {
  assert.equal(
    resolveStandaloneViewerSourceFormat('usd', { renderSelectedUsdFromRobotState: true }),
    'urdf',
  );
});

test('resolveStandaloneViewerSourceFormat never exposes USD as a visible renderer format', () => {
  assert.equal(resolveStandaloneViewerSourceFormat('usd'), 'urdf');
});

test('resolveStandaloneViewerContent keeps standalone MJCF viewer reloads pinned to the MJCF source', () => {
  assert.equal(
    resolveStandaloneViewerContent({
      selectedFileFormat: 'mjcf',
      selectedFileContent: '<mujoco model="original" />',
      resolvedMjcfSourceContent: '<mujoco model="resolved" />',
      viewerUrdfContent: '<robot name="fallback" />',
      viewerGeneratedUrdfContent: '<robot name="generated" />',
      isSelectedUsdHydrating: false,
    }),
    '<mujoco model="resolved" />',
  );
});

test('resolveStandaloneViewerContent hides raw USD content while a USD source is loading', () => {
  assert.equal(
    resolveStandaloneViewerContent({
      selectedFileFormat: 'usd',
      selectedFileContent: '#usda 1.0',
      resolvedMjcfSourceContent: '<mujoco />',
      viewerUrdfContent: '<robot />',
      viewerGeneratedUrdfContent: '<robot name="generated" />',
      isSelectedUsdHydrating: true,
    }),
    USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF,
  );
});

test('resolveStandaloneViewerContent uses a valid placeholder URDF for RobotState-rendered USD', () => {
  assert.equal(
    resolveStandaloneViewerContent({
      selectedFileFormat: 'usd',
      selectedFileContent: '#usda 1.0',
      resolvedMjcfSourceContent: '<mujoco />',
      viewerUrdfContent: '<robot />',
      viewerGeneratedUrdfContent: '<robot name="generated" />',
      isSelectedUsdHydrating: true,
      renderSelectedUsdFromRobotState: true,
    }),
    USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF,
  );
});

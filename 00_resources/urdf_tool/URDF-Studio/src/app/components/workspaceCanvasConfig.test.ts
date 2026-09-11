import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveWorkspaceCanvasEnvironmentIntensity } from './workspaceCanvasConfig';

test('resolveWorkspaceCanvasEnvironmentIntensity prefers the theme override when present', () => {
  assert.equal(
    resolveWorkspaceCanvasEnvironmentIntensity({
      effectiveTheme: 'light',
      environmentIntensity: 0.36,
      environmentIntensityByTheme: {
        light: 0.42,
        dark: 0.4,
      },
    }),
    0.42,
  );

  assert.equal(
    resolveWorkspaceCanvasEnvironmentIntensity({
      effectiveTheme: 'dark',
      environmentIntensity: 0.36,
      environmentIntensityByTheme: {
        light: 0.42,
        dark: 0.4,
      },
    }),
    0.4,
  );
});

test('resolveWorkspaceCanvasEnvironmentIntensity falls back to the explicit intensity', () => {
  assert.equal(
    resolveWorkspaceCanvasEnvironmentIntensity({
      effectiveTheme: 'dark',
      environmentIntensity: 0.36,
    }),
    0.36,
  );
});

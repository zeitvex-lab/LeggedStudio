import assert from 'node:assert/strict';
import test from 'node:test';

import { isDevelopmentBuild } from './runtimeDiagnostics.ts';

test('isDevelopmentBuild falls back to NODE_ENV outside Vite runtime env', () => {
  const originalNodeEnv = process.env.NODE_ENV;

  try {
    process.env.NODE_ENV = 'development';
    assert.equal(isDevelopmentBuild(), true);

    process.env.NODE_ENV = 'production';
    assert.equal(isDevelopmentBuild(), false);
  } finally {
    if (originalNodeEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = originalNodeEnv;
    }
  }
});

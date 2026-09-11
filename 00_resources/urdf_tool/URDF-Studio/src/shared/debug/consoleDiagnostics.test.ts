import assert from 'node:assert/strict';
import test from 'node:test';

import { shouldEmitRegressionConsoleDiagnostics } from './consoleDiagnostics.ts';

test('shouldEmitRegressionConsoleDiagnostics requires regressionDebug=1', () => {
  assert.equal(
    shouldEmitRegressionConsoleDiagnostics({ location: { search: '' } } as Window),
    false,
  );
  assert.equal(
    shouldEmitRegressionConsoleDiagnostics({
      location: { search: '?regressionDebug=1' },
    } as Window),
    true,
  );
});

test('shouldEmitRegressionConsoleDiagnostics stays off outside the browser', () => {
  assert.equal(shouldEmitRegressionConsoleDiagnostics(null), false);
});

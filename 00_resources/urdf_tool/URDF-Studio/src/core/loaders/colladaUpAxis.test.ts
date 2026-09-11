import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizeColladaUpAxis } from './colladaUpAxis';

test('normalizeColladaUpAxis rewrites Z_UP documents to Y_UP without touching other content', () => {
  const input = `<?xml version="1.0"?>
<COLLADA>
  <asset>
    <up_axis>Z_UP</up_axis>
  </asset>
</COLLADA>`;

  const result = normalizeColladaUpAxis(input);

  assert.equal(result.normalized, true);
  assert.match(result.content, /<up_axis>Y_UP<\/up_axis>/);
  assert.doesNotMatch(result.content, /<up_axis>Z_UP<\/up_axis>/);
});

test('normalizeColladaUpAxis leaves non-Z_UP documents unchanged', () => {
  const input = `<?xml version="1.0"?>
<COLLADA>
  <asset>
    <up_axis>Y_UP</up_axis>
  </asset>
</COLLADA>`;

  const result = normalizeColladaUpAxis(input);

  assert.equal(result.normalized, false);
  assert.equal(result.content, input);
});

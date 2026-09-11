import test from 'node:test';
import assert from 'node:assert/strict';

test('property-editor utils barrel exposes detail link tab helpers', async () => {
  const moduleUnderTest = await import('./index.ts');

  assert.equal(typeof moduleUnderTest.resolveDetailLinkTabAfterGeometrySelection, 'function');
  assert.equal(typeof moduleUnderTest.resolveDetailLinkTabAfterViewerMeshSelect, 'function');
});

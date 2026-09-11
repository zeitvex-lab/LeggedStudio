import assert from 'node:assert/strict';
import test from 'node:test';

import {
  resolveDetailLinkTabAfterGeometrySelection,
  resolveDetailLinkTabAfterViewerMeshSelect,
} from './detailLinkTab.ts';

test('viewer visual mesh selection switches to the visual tab', () => {
  assert.equal(
    resolveDetailLinkTabAfterViewerMeshSelect('editor', 'collision', 'visual'),
    'visual',
  );
  assert.equal(resolveDetailLinkTabAfterViewerMeshSelect('editor', 'visual', 'visual'), 'visual');
  assert.equal(resolveDetailLinkTabAfterViewerMeshSelect('editor', 'physics', 'visual'), 'visual');
});

test('viewer collision mesh selection switches to the collision tab', () => {
  assert.equal(
    resolveDetailLinkTabAfterViewerMeshSelect('editor', 'visual', 'collision'),
    'collision',
  );
  assert.equal(
    resolveDetailLinkTabAfterViewerMeshSelect('editor', 'physics', 'collision'),
    'collision',
  );
});

test('editor mesh selection keeps the same tab-switch policy regardless of prior tab', () => {
  assert.equal(
    resolveDetailLinkTabAfterViewerMeshSelect('editor', 'collision', 'visual'),
    'visual',
  );
  assert.equal(
    resolveDetailLinkTabAfterViewerMeshSelect('editor', 'physics', 'collision'),
    'collision',
  );
  assert.equal(resolveDetailLinkTabAfterViewerMeshSelect('editor', 'physics', 'visual'), 'visual');
});

test('explicit geometry selection follows the chosen geometry subtype', () => {
  assert.equal(resolveDetailLinkTabAfterGeometrySelection('visual', 'visual'), 'visual');
  assert.equal(resolveDetailLinkTabAfterGeometrySelection('collision', 'visual'), 'collision');
  assert.equal(resolveDetailLinkTabAfterGeometrySelection('visual', 'physics'), 'visual');
});

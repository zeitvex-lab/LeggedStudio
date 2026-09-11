import assert from 'node:assert/strict';
import test from 'node:test';

import {
  accumulateSourceCodeDirtyRanges,
  shouldResetSourceCodeEditorSession,
} from './sourceCodeEditorSession';

test('shouldResetSourceCodeEditorSession ignores code sync within the same document session', () => {
  const previousBoundary = {
    documentId: 'robot.urdf',
    validationEnabled: true,
  };
  const nextBoundary = {
    documentId: 'robot.urdf',
    validationEnabled: true,
  };

  assert.equal(shouldResetSourceCodeEditorSession(previousBoundary, nextBoundary), false);
});

test('shouldResetSourceCodeEditorSession resets when the active document changes', () => {
  const previousBoundary = {
    documentId: 'robot.urdf',
    validationEnabled: true,
  };
  const nextBoundary = {
    documentId: 'robot_v2.urdf',
    validationEnabled: true,
  };

  assert.equal(shouldResetSourceCodeEditorSession(previousBoundary, nextBoundary), true);
});

test('shouldResetSourceCodeEditorSession resets when validation mode changes', () => {
  const previousBoundary = {
    documentId: 'robot.urdf',
    validationEnabled: false,
  };
  const nextBoundary = {
    documentId: 'robot.urdf',
    validationEnabled: true,
  };

  assert.equal(shouldResetSourceCodeEditorSession(previousBoundary, nextBoundary), true);
});

test('accumulateSourceCodeDirtyRanges rebases existing ranges through earlier inserts', () => {
  const ranges = accumulateSourceCodeDirtyRanges(
    [{ startOffset: 10, endOffset: 15 }],
    [{ rangeOffset: 4, rangeLength: 1, text: 'wxyz' }],
  );

  assert.deepEqual(ranges, [
    { startOffset: 4, endOffset: 8 },
    { startOffset: 13, endOffset: 18 },
  ]);
});

test('accumulateSourceCodeDirtyRanges merges edits that land inside an existing dirty range', () => {
  const ranges = accumulateSourceCodeDirtyRanges(
    [{ startOffset: 10, endOffset: 15 }],
    [{ rangeOffset: 12, rangeLength: 1, text: 'abcd' }],
  );

  assert.deepEqual(ranges, [{ startOffset: 10, endOffset: 18 }]);
});

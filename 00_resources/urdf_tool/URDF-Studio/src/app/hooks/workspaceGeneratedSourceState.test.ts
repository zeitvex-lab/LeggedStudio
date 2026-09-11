import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotFile } from '@/types';

import { buildGeneratedWorkspaceFileState } from './workspaceGeneratedSourceState.ts';

function createFile(name: string, content: string): RobotFile {
  return {
    name,
    content,
    format: 'urdf',
  };
}

test('buildGeneratedWorkspaceFileState appends a new generated workspace file', () => {
  const existing = createFile('existing.urdf', '<existing />');
  const generated = createFile('workspace/generated.urdf', '<generated />');

  const result = buildGeneratedWorkspaceFileState({
    availableFiles: [existing],
    allFileContents: { [existing.name]: existing.content },
    file: generated,
  });

  assert.equal(result.nextSelectedFile.name, generated.name);
  assert.equal(result.nextAvailableFiles.length, 2);
  assert.equal(result.nextAllFileContents[generated.name], generated.content);
});

test('buildGeneratedWorkspaceFileState replaces an existing generated workspace file in place', () => {
  const generatedBefore = createFile('workspace/generated.urdf', '<before />');
  const generatedAfter = createFile('workspace/generated.urdf', '<after />');

  const result = buildGeneratedWorkspaceFileState({
    availableFiles: [generatedBefore],
    allFileContents: { [generatedBefore.name]: generatedBefore.content },
    file: generatedAfter,
  });

  assert.equal(result.nextAvailableFiles.length, 1);
  assert.equal(result.nextSelectedFile.content, '<after />');
  assert.equal(result.nextAvailableFiles[0]?.content, '<after />');
  assert.equal(result.nextAllFileContents[generatedAfter.name], '<after />');
});

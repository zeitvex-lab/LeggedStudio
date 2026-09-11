import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const sharedRuntimeFiles = [
  new URL('./3d/LinkIkTransformControls.tsx', import.meta.url),
  new URL('./Panel/JointControlItem.tsx', import.meta.url),
];

test('shared runtime components do not import app stores directly', async () => {
  for (const fileUrl of sharedRuntimeFiles) {
    const source = await readFile(fileUrl, 'utf8');
    assert.doesNotMatch(source, /from ['"]@\/store(?:\/[^'"]*)?['"]/);
    assert.doesNotMatch(source, /use(?:Robot|UI|Assembly|Selection)Store/);
  }
});

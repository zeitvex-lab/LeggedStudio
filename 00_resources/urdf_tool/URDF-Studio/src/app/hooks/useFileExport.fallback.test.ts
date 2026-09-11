import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const sourcePath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), './useFileExport.ts');

test('useFileExport does not synthesize an empty_root fallback robot for workspace exports', async () => {
  const source = await readFile(sourcePath, 'utf8');

  assert.doesNotMatch(source, /empty_root|base_link[\s\S]*GeometryType\.NONE[\s\S]*mass:\s*0/m);
});

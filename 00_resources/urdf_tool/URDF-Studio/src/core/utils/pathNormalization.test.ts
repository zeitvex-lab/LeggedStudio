import test from 'node:test';
import assert from 'node:assert/strict';

import { normalizeRelativePath } from './pathNormalization.ts';

test('normalizeRelativePath normalizes relative paths without preserving leading roots', () => {
  const cases: Array<[input: string, expected: string]> = [
    ['', ''],
    ['.', ''],
    ['./meshes//wheel.dae', 'meshes/wheel.dae'],
    ['robots\\demo\\.\\meshes\\wheel.dae', 'robots/demo/meshes/wheel.dae'],
    ['/absolute/./meshes/part.stl', 'absolute/meshes/part.stl'],
    ['../outside/mesh.stl', 'outside/mesh.stl'],
    ['robots/demo/../../mesh.stl', 'mesh.stl'],
    ['robots/demo/..', 'robots'],
  ];

  for (const [input, expected] of cases) {
    assert.equal(normalizeRelativePath(input), expected, input);
  }
});

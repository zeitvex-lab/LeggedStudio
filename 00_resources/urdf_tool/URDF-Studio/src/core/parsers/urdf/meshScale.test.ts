import test from 'node:test';
import assert from 'node:assert/strict';

import { formatUrdfMeshScaleAttribute } from './meshScale.ts';

test('omits mesh scale attribute for identity scale', () => {
  const attribute = formatUrdfMeshScaleAttribute(
    { x: 1, y: 1, z: 1 },
    (value) => value.toString(),
  );

  assert.equal(attribute, '');
});

test('writes mesh scale attribute for non-uniform scale', () => {
  const attribute = formatUrdfMeshScaleAttribute(
    { x: 0.5, y: 1.25, z: 2 },
    (value) => value.toString(),
  );

  assert.equal(attribute, ' scale="0.5 1.25 2"');
});

test('treats missing scale values as identity', () => {
  const attribute = formatUrdfMeshScaleAttribute(
    undefined,
    (value) => value.toString(),
  );

  assert.equal(attribute, '');
});

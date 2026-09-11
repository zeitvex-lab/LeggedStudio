import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildMeshScaleAttribute,
  isIdentityMeshScale,
} from './meshScaleSerialization.ts';

test('omits mesh scale attribute for the identity scale', () => {
  assert.equal(
    buildMeshScaleAttribute({ x: 1, y: 1, z: 1 }, (value) => String(value)),
    '',
  );
  assert.equal(isIdentityMeshScale({ x: 1, y: 1, z: 1 }), true);
});

test('serializes non-uniform mesh scale as a URDF attribute', () => {
  assert.equal(
    buildMeshScaleAttribute(
      { x: 0.5, y: 1.25, z: 2 },
      (value) => value.toFixed(3).replace(/\.?0+$/, ''),
    ),
    ' scale="0.5 1.25 2"',
  );
});

test('treats undefined axes as identity defaults when checking scale', () => {
  assert.equal(isIdentityMeshScale({ x: 1, y: undefined as unknown as number, z: 1 }), true);
  assert.equal(isIdentityMeshScale(undefined), true);
});

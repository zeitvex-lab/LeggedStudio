import assert from 'node:assert/strict';
import test from 'node:test';

import type { UrdfVisualMaterial } from '@/types';

import {
  clampMaterialOpacity,
  getAuthoredMaterialOpacity,
  getUniqueAuthoredMaterialColors,
  normalizeMaterialColor,
  withAuthoredMaterialOpacity,
} from './geometryMaterial.ts';

test('clampMaterialOpacity keeps material alpha finite and in range', () => {
  assert.equal(clampMaterialOpacity(-0.4), 0);
  assert.equal(clampMaterialOpacity(0.45), 0.45);
  assert.equal(clampMaterialOpacity(2), 1);
  assert.equal(clampMaterialOpacity(Number.NaN), 1);
});

test('getAuthoredMaterialOpacity resolves explicit opacity, rgba alpha, color alpha, and fallback color', () => {
  assert.equal(getAuthoredMaterialOpacity({ opacity: 1.4 }), 1);
  assert.equal(getAuthoredMaterialOpacity({ colorRgba: [0.1, 0.2, 0.3, -1] }), 0);
  assert.equal(getAuthoredMaterialOpacity({ color: '#12345680' }), 0.5019607843137255);
  assert.equal(getAuthoredMaterialOpacity({}, '#ffffff40'), 0.25098039215686274);
});

test('withAuthoredMaterialOpacity updates alpha fields without mutating the source material', () => {
  const material: UrdfVisualMaterial = {
    name: 'paint',
    color: '#123456',
    colorRgba: [0.1, 0.2, 0.3, 0.4],
    roughness: 0.7,
  };

  const updated = withAuthoredMaterialOpacity(material, 0.25);

  assert.deepEqual(updated, {
    name: 'paint',
    color: '#12345640',
    colorRgba: [0.1, 0.2, 0.3, 0.25],
    opacity: 0.25,
    roughness: 0.7,
  });
  assert.deepEqual(material, {
    name: 'paint',
    color: '#123456',
    colorRgba: [0.1, 0.2, 0.3, 0.4],
    roughness: 0.7,
  });
});

test('getUniqueAuthoredMaterialColors preserves first display colors while de-duping normalized values', () => {
  assert.equal(normalizeMaterialColor('  #ABCDEF  '), '#abcdef');
  assert.deepEqual(
    getUniqueAuthoredMaterialColors([
      { color: ' #ABCDEF ' },
      { color: '#abcdef' },
      { color: '' },
      { color: ' #12345680 ' },
    ]),
    ['#ABCDEF', '#12345680'],
  );
});

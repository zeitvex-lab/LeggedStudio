import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FUSION_ROTATE_ARC_MAX_RADIUS,
  FUSION_ROTATE_ARC_RADIUS,
  FUSION_ROTATE_FULL_CIRCLE,
  type FusionRotateAxisName,
  getFusionRotateArcAngles,
  getFusionRotateArcPoint,
  getFusionRotateArcRadius,
  resolveFusionTranslateShaftStart,
} from './fusionRotateKnob.ts';
import {
  THICK_ROTATE_ARC_RADIUS,
  THICK_TRANSLATE_SHAFT_RADIUS,
  TRANSLATE_ARROW_HANDLE_OFFSET,
  TRANSLATE_CENTER_GAP,
} from './gizmoCore.ts';

test('fusion rotate rings form a centered shared CAD trackball', () => {
  const axes: FusionRotateAxisName[] = ['X', 'Y', 'Z'];

  for (const axis of axes) {
    const angles = getFusionRotateArcAngles(axis);
    assert.equal(getFusionRotateArcRadius(axis), FUSION_ROTATE_ARC_RADIUS);
    assert.equal(angles.start, 0);
    assert.equal(angles.end, FUSION_ROTATE_FULL_CIRCLE);
    assert.equal(FUSION_ROTATE_ARC_MAX_RADIUS, FUSION_ROTATE_ARC_RADIUS);
  }
});

test('getFusionRotateArcPoint keeps ring samples on their axis planes', () => {
  const xPoint = getFusionRotateArcPoint('X', Math.PI / 3);
  const yPoint = getFusionRotateArcPoint('Y', Math.PI / 3);
  const zPoint = getFusionRotateArcPoint('Z', Math.PI / 3);

  assert.ok(Math.abs(xPoint.x) < 1e-9);
  assert.ok(Math.abs(yPoint.y) < 1e-9);
  assert.ok(Math.abs(zPoint.z) < 1e-9);
  assert.ok(Math.abs(xPoint.length() - FUSION_ROTATE_ARC_RADIUS) < 1e-9);
  assert.ok(Math.abs(yPoint.length() - FUSION_ROTATE_ARC_RADIUS) < 1e-9);
  assert.ok(Math.abs(zPoint.length() - FUSION_ROTATE_ARC_RADIUS) < 1e-9);
});

test('resolveFusionTranslateShaftStart keeps visible shafts clear of rotate rings', () => {
  const shaftStart = resolveFusionTranslateShaftStart();
  const minimumClearStart =
    FUSION_ROTATE_ARC_MAX_RADIUS + THICK_ROTATE_ARC_RADIUS + THICK_TRANSLATE_SHAFT_RADIUS;

  assert.ok(shaftStart > minimumClearStart);
  assert.ok(shaftStart > TRANSLATE_CENTER_GAP);
  assert.ok(shaftStart < TRANSLATE_ARROW_HANDLE_OFFSET);
});

import test from 'node:test';
import assert from 'node:assert/strict';

import { isLikelyNonRenderableUsdConfigPath, pickPreferredUsdRootFile } from './usdFormatUtils.ts';

test('treats configuration sidecar USD files as non-root candidates', () => {
  assert.equal(
    isLikelyNonRenderableUsdConfigPath('Go2/usd/configuration/go2_description_physics.usd'),
    true,
  );
  assert.equal(isLikelyNonRenderableUsdConfigPath('Go2/usd/go2.usd'), false);
});

test('prefers the top-level robot USD over configuration sidecars', () => {
  const files = [
    { name: 'Go2/usd/configuration/go2_description_physics.usd' },
    { name: 'Go2/usd/configuration/go2_description_sensor.usd' },
    { name: 'Go2/usd/go2.usd' },
    { name: 'Go2/usd/configuration/go2_description_base.usd' },
  ];

  const selected = pickPreferredUsdRootFile(files);
  assert.equal(selected?.name, 'Go2/usd/go2.usd');
});

test('prefers viewer roundtrip USD roots over raw Unitree package roots', () => {
  const files = [
    { name: 'unitree_model/B2/usd/b2.usd' },
    { name: 'unitree_model/B2/usd/b2.viewer_roundtrip.usd' },
    { name: 'unitree_model/B2/usd/configuration/b2_description_base.usd' },
    { name: 'unitree_model/Go2/usd/go2.viewer_roundtrip.usd' },
  ];

  const selected = pickPreferredUsdRootFile(files);
  assert.equal(selected?.name, 'unitree_model/B2/usd/b2.viewer_roundtrip.usd');
});

test('prefers canonical Unitree USDA roots over mode and hand variants', () => {
  const files = [
    { name: 'g1_description/g1_23dof_mode_10.usda' },
    { name: 'g1_description/g1_23dof.usda' },
    { name: 'g1_description/g1_29dof_with_hand.usda' },
    { name: 'g1_description/g1_29dof_lock_waist.usda' },
    { name: 'g1_description/configuration/g1_23dof_base.usda' },
  ];

  const selected = pickPreferredUsdRootFile(files);
  assert.equal(selected?.name, 'g1_description/g1_23dof.usda');
});

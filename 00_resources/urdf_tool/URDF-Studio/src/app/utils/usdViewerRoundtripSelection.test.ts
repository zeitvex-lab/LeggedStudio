import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveUsdViewerRoundtripSelection } from './usdViewerRoundtripSelection.ts';
import type { RobotFile } from '@/types';

function usdFile(name: string): RobotFile {
  return { name, format: 'usd', content: '' };
}

test('maps raw Unitree USD roots to sibling viewer roundtrip files', () => {
  const rawFile = usdFile('unitree_model/B2/usd/b2.usd');
  const roundtripFile = usdFile('unitree_model/B2/usd/b2.viewer_roundtrip.usd');

  assert.equal(
    resolveUsdViewerRoundtripSelection(rawFile, [rawFile, roundtripFile]),
    roundtripFile,
  );
});

test('keeps USD files unchanged when no sibling viewer roundtrip exists', () => {
  const rawFile = usdFile('unitree_model/H1/h1/usd/h1.usd');

  assert.equal(resolveUsdViewerRoundtripSelection(rawFile, [rawFile]), rawFile);
});

test('keeps already selected viewer roundtrip USD files unchanged', () => {
  const roundtripFile = usdFile('unitree_model/Go2/usd/go2.viewer_roundtrip.usd');

  assert.equal(resolveUsdViewerRoundtripSelection(roundtripFile, [roundtripFile]), roundtripFile);
});

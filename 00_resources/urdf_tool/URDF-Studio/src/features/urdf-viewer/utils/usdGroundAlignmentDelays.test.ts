import test from 'node:test';
import assert from 'node:assert/strict';

import {
  resolveUsdGroundAlignmentSettleDelaysMs,
} from './usdGroundAlignmentDelays.ts';

test('uses the same USD ground alignment settle delays for every stage', () => {
  const delays = resolveUsdGroundAlignmentSettleDelaysMs('/unitree_model/B2/usd/b2.usd');
  assert.equal(delays.includes(1600), true);
  assert.equal(delays.includes(3000), true);
  assert.deepEqual(
    resolveUsdGroundAlignmentSettleDelaysMs('/unitree_model/Go2/usd/go2.usd'),
    delays,
  );
  assert.deepEqual(
    resolveUsdGroundAlignmentSettleDelaysMs('custom_robot.usd'),
    delays,
  );
});

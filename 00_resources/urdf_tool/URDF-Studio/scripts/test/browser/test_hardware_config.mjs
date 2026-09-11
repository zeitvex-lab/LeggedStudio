#!/usr/bin/env node

/**
 * Hardware/Motor Configuration browser regression test.
 *
 * Covers: accessing joint hardware field, setting hardware config,
 *         verifying persistence, undo.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert, assertEqual,
  importModel, waitForReady, getTopology,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

async function main() {
  const suite = createTestSuite('Hardware/Motor Config');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);
    const topo = await getTopology(page);
    assert(suite, topo.jointCount > 0, 'model has joints');

    // ── 1. Check hardware field accessible ──
    const hipJoint = topo.joints.find((j) => j.type === 'revolute');
    assert(suite, !!hipJoint, 'revolute joint found');

    // Hardware field may be null initially
    const hwBefore = hipJoint.hardware;
    assert(suite, hwBefore === null || hwBefore === undefined || typeof hwBefore === 'object',
      'hardware field accessible (null or object)');

    // ── 2. Set hardware config ──
    const hwConfig = {
      armature: 0.1,
      brand: 'test_brand',
      motorType: 'test_motor',
      motorId: 'test_motor_001',
      motorDirection: 1,
    };
    await store.updateJoint(page, hipJoint.id, { hardware: hwConfig });
    await delay(200);

    // ── 3. Verify hardware persisted ──
    const topo2 = await getTopology(page);
    const j2 = topo2.joints.find((j) => j.id === hipJoint.id);
    assert(suite, j2.hardware != null, 'hardware config persisted');
    assertEqual(suite, j2.hardware?.motorId, 'test_motor_001', 'motor id persisted');

    // ── 4. Undo hardware config ──
    await store.undo(page); await delay(200);
    const topo3 = await getTopology(page);
    const j3 = topo3.joints.find((j) => j.id === hipJoint.id);
    assert(suite, j3.hardware == null || j3.hardware?.motorId !== 'test_motor_001',
      'hardware config undone');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('hardware_config', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

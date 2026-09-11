#!/usr/bin/env node

/**
 * IK Drag Interaction browser regression test.
 *
 * Covers: setting translate tool mode, verifying interaction targets,
 *         simulating canvas mouse drag.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert,
  importModel, waitForReady, getTopology, getRuntimeTransforms,
  store, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

async function main() {
  const suite = createTestSuite('IK Drag Interaction');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, 'franka_emika_panda', 'panda.xml');
    await waitForReady(page);
    const topo = await getTopology(page);
    assert(suite, topo.linkCount > 0, 'panda model loaded');

    // ── 1. Set translate tool mode ──
    const translateResult = await store.setViewerToolMode(page, 'translate');
    assert(suite, translateResult?.ok, 'tool mode → translate');
    await delay(300);

    // ── 2. Verify no errors after tool mode change ──
    const errs1 = session.errors();
    assert(suite, errs1.page.length === 0, 'no errors after translate mode');

    // ── 3. Simulate mouse interaction on canvas ──
    const canvasExists = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      return canvas instanceof HTMLCanvasElement;
    });
    assert(suite, canvasExists, 'canvas exists');

    // Click on canvas center to trigger potential interaction
    const canvasBox = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!(canvas instanceof HTMLCanvasElement)) return null;
      const rect = canvas.getBoundingClientRect();
      return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2, w: rect.width, h: rect.height };
    });

    if (canvasBox) {
      await page.mouse.move(canvasBox.x, canvasBox.y);
      await page.mouse.down();
      await page.mouse.move(canvasBox.x + 50, canvasBox.y - 30, { steps: 5 });
      await page.mouse.up();
      await delay(200);
    }

    // ── 4. Verify runtime transforms still valid after drag ──
    const rt = await getRuntimeTransforms(page);
    assert(suite, rt.length > 0, 'runtime transforms still present after drag');

    // ── 5. Switch back to select mode ──
    await store.setViewerToolMode(page, 'select');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors overall');
  } finally {
    await session.cleanup();
  }

  await writeReport('ik_drag', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

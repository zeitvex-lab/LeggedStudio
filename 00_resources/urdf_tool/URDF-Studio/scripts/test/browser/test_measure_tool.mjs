#!/usr/bin/env node

/**
 * Measure Tool browser regression test.
 *
 * Covers: switching to measure mode, the point/object mode switch, placing two
 *         free surface points in point mode (distance + decoupled from selection),
 *         object-mode controls, and cycling through the other tool modes.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert,
  importModel, waitForReady, store, getProjectedInteractionTargets,
  clickCanvasTarget, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

// Number of <select> controls rendered inside the measure panel. Object mode shows
// the anchor selector (inside the collapsed Advanced section, still in the DOM);
// point mode hides every object-only control, so it renders none.
async function measurePanelSelectCount(page) {
  return page.evaluate(() => document.querySelectorAll('.measure-panel select').length);
}

async function measurePanelText(page) {
  return page.evaluate(() => document.querySelector('.measure-panel')?.textContent ?? '');
}

// Click the segmented-control item for the requested measure mode (language agnostic).
async function clickMeasureModeSegment(page, mode) {
  return page.evaluate((targetMode) => {
    const labels = targetMode === 'point' ? ['Point', '点到点'] : ['Object', '对象测量'];
    const buttons = [...document.querySelectorAll('.measure-panel button')];
    const button = buttons.find((el) => labels.includes((el.textContent ?? '').trim()));
    if (!button) return false;
    button.click();
    return true;
  }, mode);
}

async function main() {
  const suite = createTestSuite('Measure Tool');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);

    // ── 1. Switch to measure mode ──
    const measureResult = await store.setViewerToolMode(page, 'measure');
    assert(suite, measureResult?.ok, 'tool mode → measure accepted');
    await delay(300);

    const errs1 = session.errors();
    assert(suite, errs1.page.length === 0, 'no page errors after measure mode');

    // ── 2. Object mode is the default and renders the anchor selector ──
    const objectSelectCount = await measurePanelSelectCount(page);
    assert(suite, objectSelectCount >= 1, 'object mode renders the anchor selector');

    // ── 3. Switch to point mode via the segmented control ──
    const switchedToPoint = await clickMeasureModeSegment(page, 'point');
    assert(suite, switchedToPoint, 'point-mode segment is clickable');
    await delay(300);

    const pointSelectCount = await measurePanelSelectCount(page);
    assert(suite, pointSelectCount === 0, 'point mode hides object-only selectors');

    // ── 4. Place two free surface points and confirm a measurement is produced ──
    const targets = await getProjectedInteractionTargets(page);
    assert(suite, targets.length >= 1, 'projected robot target available for picking');

    const firstTarget = targets[0];
    // Second point: the farthest other projected target if the debug bridge exposes
    // more than one, otherwise the canvas centre (which lands on the go2 body) so the
    // two surface points are well separated and yield a clearly non-zero span.
    const canvasCenter = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!(canvas instanceof HTMLCanvasElement)) return null;
      const rect = canvas.getBoundingClientRect();
      return { clientX: rect.x + rect.width / 2, clientY: rect.y + rect.height / 2 };
    });
    const secondTarget = targets
      .slice(1)
      .reduce(
        (best, t) => {
          const d = Math.hypot(t.clientX - firstTarget.clientX, t.clientY - firstTarget.clientY);
          return d > best.d ? { t, d } : best;
        },
        { t: canvasCenter, d: 0 },
      ).t;

    await clickCanvasTarget(page, firstTarget);
    await delay(200);
    const afterFirstClick = await measurePanelText(page);
    assert(
      suite,
      /\(-?\d+\.\d{3}, -?\d+\.\d{3}, -?\d+\.\d{3}\)/.test(afterFirstClick),
      'first point click records a surface coordinate',
    );

    // The point click must NOT select a link (selection stays empty).
    const selectionAfterPoint = await page.evaluate(() => {
      const snap = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.();
      return snap?.interaction?.selection ?? snap?.selection ?? null;
    });
    assert(
      suite,
      !selectionAfterPoint || !selectionAfterPoint.id,
      'point-mode click does not select a link',
    );

    await clickCanvasTarget(page, secondTarget);
    await delay(200);
    const afterSecondClick = await measurePanelText(page);
    const distanceMatch = afterSecondClick.match(/(\d+\.\d{4})m/);
    assert(suite, Boolean(distanceMatch), 'completed point pair shows a total distance');
    assert(
      suite,
      distanceMatch ? Number(distanceMatch[1]) > 0 : false,
      'measured distance between two surface points is non-zero',
    );

    const errs2 = session.errors();
    assert(suite, errs2.page.length === 0, 'no page errors after point measuring');

    // ── 5. Switch back to object mode ──
    const switchedToObject = await clickMeasureModeSegment(page, 'object');
    assert(suite, switchedToObject, 'object-mode segment is clickable');
    await delay(200);
    const objectSelectCountAgain = await measurePanelSelectCount(page);
    assert(suite, objectSelectCountAgain >= 1, 'object mode restores the anchor selector');

    // ── 6. Switch back to select mode and cycle other tool modes ──
    const selectResult = await store.setViewerToolMode(page, 'select');
    assert(suite, selectResult?.ok, 'tool mode → select accepted');
    await delay(200);

    for (const mode of ['translate', 'rotate', 'view']) {
      const result = await store.setViewerToolMode(page, mode);
      assert(suite, result?.ok, `tool mode → ${mode} accepted`);
      await delay(100);
    }

    await store.setViewerToolMode(page, 'select');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors overall');
  } finally {
    await session.cleanup();
  }

  await writeReport('measure_tool', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

#!/usr/bin/env node

/**
 * Language Switching browser regression test.
 *
 * Covers: detecting current language, switching language, verifying UI changes,
 *         and keeping canonical Component properties fully localized.
 */

import { setTimeout as delay } from 'node:timers/promises';
import {
  createSession, createTestSuite, assert,
  importModel, waitForReady, writeReport, printSummary,
} from './helpers/mjcf-helpers.mjs';

async function main() {
  const suite = createTestSuite('Language Switching');
  const session = await createSession();
  const { page } = session;

  try {
    await importModel(page, 'unitree_go2', 'go2.xml');
    await waitForReady(page);

    // ── 1. Detect current language ──
    const currentLang = await page.evaluate(() => {
      const el = document.documentElement;
      return {
        lang: el.getAttribute('lang'),
        dataLang: el.getAttribute('data-lang'),
        storeLang: window.__URDF_STUDIO_DEBUG__?.__uiStore__?.getState?.()?.lang,
      };
    });
    assert(suite, currentLang.storeLang === 'en' || currentLang.storeLang === 'zh',
      'current language readable from ui store');

    // ── 2. Switch language via store ──
    const switchResult = await page.evaluate(() => {
      const store = window.__URDF_STUDIO_DEBUG__?.__uiStore__?.getState?.();
      if (!store?.setLang) return { ok: false };
      const current = store.lang;
      const next = current === 'en' ? 'zh' : 'en';
      store.setLang(next);
      return { ok: true, from: current, to: next };
    });
    assert(suite, switchResult?.ok, 'language switched via store');
    await delay(300);

    // ── 3. Verify UI labels changed ──
    const afterSwitch = await page.evaluate(() => {
      const el = document.documentElement;
      return {
        lang: el.getAttribute('lang'),
        dataLang: el.getAttribute('data-lang'),
        storeLang: window.__URDF_STUDIO_DEBUG__?.__uiStore__?.getState?.()?.lang,
        bodyText: document.body?.innerText?.slice(0, 500) ?? '',
      };
    });
    assert(suite, afterSwitch.storeLang === switchResult.to, 'store language updated');
    assert(suite, afterSwitch.dataLang === switchResult.to, 'document data-lang updated');

    // ── 4. Component properties stay fully localized ──
    const componentSelection = await page.evaluate(() => {
      const api = window.__URDF_STUDIO_DEBUG__;
      const componentId = Object.keys(
        api?.__workspaceStore__?.getState?.()?.workspace?.components ?? {},
      )[0];
      if (!componentId) return { ok: false, componentId: null };

      api?.__uiStore__?.getState?.()?.setLang?.('zh');
      api?.__selectionStore__?.getState?.()?.setSelection?.({
        entity: { type: 'component', componentId },
      });
      return { ok: true, componentId };
    });
    assert(suite, componentSelection.ok, 'component selected for localization check');
    await page.waitForSelector('[data-testid="component-properties"]');
    await delay(200);

    const componentPropertyText = await page.evaluate(() =>
      document.querySelector('[data-testid="property-editor-sidebar-content"]')?.innerText ?? '');
    assert(suite, componentPropertyText.includes('组件'), 'component kind localized to Chinese');
    assert(suite, componentPropertyText.includes('变换'), 'component transform localized to Chinese');
    assert(suite, componentPropertyText.includes('位置'), 'component position localized to Chinese');
    assert(suite, componentPropertyText.includes('旋转'), 'component rotation localized to Chinese');
    assert(suite, !/\bcomponent\b/i.test(componentPropertyText), 'raw component kind is not exposed');
    assert(suite, !/position-|rotation-/i.test(componentPropertyText),
      'raw transform field identifiers are not exposed');

    // ── 5. Switch back ──
    await page.evaluate((from) => {
      const store = window.__URDF_STUDIO_DEBUG__?.__uiStore__?.getState?.();
      store?.setLang?.(from);
    }, switchResult.from);
    await delay(200);

    const restored = await page.evaluate(() =>
      window.__URDF_STUDIO_DEBUG__?.__uiStore__?.getState?.()?.lang);
    assert(suite, restored === switchResult.from, 'language restored');

    const errs = session.errors();
    assert(suite, errs.page.length === 0, 'no page errors');
  } finally {
    await session.cleanup();
  }

  await writeReport('language_switching', {});
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

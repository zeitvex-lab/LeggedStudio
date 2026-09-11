#!/usr/bin/env node

import { access, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

import puppeteer from 'puppeteer';

const SITE_BASE_URL = 'http://127.0.0.1:4173';
const SITE_URL = `${SITE_BASE_URL}/?regressionDebug=1`;
const FIXTURE_PATH = path.resolve('tmp/laikago_description_import.zip');
const OUTPUT_PATH = path.resolve('tmp/regression/source-editor-unitree-browser.json');
const SITE_TIMEOUT_MS = 120_000;
const STEP_TIMEOUT_MS = 60_000;

async function pathExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function isSiteReachable(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      redirect: 'follow',
      cache: 'no-store',
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function ensureSite() {
  if (await isSiteReachable(SITE_BASE_URL)) {
    return { stop: async () => {} };
  }

  const child = spawn(
    'npm',
    ['run', 'dev', '--', '--host', '127.0.0.1', '--port', '4173', '--strictPort'],
    {
      cwd: process.cwd(),
      stdio: 'inherit',
      env: process.env,
      detached: true,
    },
  );

  const deadline = Date.now() + SITE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await isSiteReachable(SITE_BASE_URL)) {
      return {
        stop: async () => {
          if (child.exitCode != null || child.signalCode != null) {
            return;
          }
          try {
            process.kill(-child.pid, 'SIGTERM');
          } catch {}
          await delay(500);
        },
      };
    }

    if (child.exitCode != null) {
      throw new Error(`dev server exited early with code ${child.exitCode}`);
    }

    await delay(500);
  }

  throw new Error(`Timed out waiting for ${SITE_BASE_URL}`);
}

async function setAutoApplyPreference(page, enabled) {
  await page.evaluate((nextEnabled) => {
    const raw = localStorage.getItem('urdf-studio-ui');
    const parsed = raw ? JSON.parse(raw) : { state: {} };
    parsed.state = {
      ...(parsed.state ?? {}),
      sourceCodeAutoApply: nextEnabled,
    };
    localStorage.setItem('urdf-studio-ui', JSON.stringify(parsed));
  }, enabled);
}

async function openPage(browser) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  const consoleErrors = [];
  const pageErrors = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({
        text: message.text(),
        location: message.location(),
      });
    }
  });

  page.on('pageerror', (error) => {
    pageErrors.push({
      message: error?.message ?? String(error),
      stack: error?.stack ?? null,
    });
  });

  await page.goto(SITE_URL, {
    waitUntil: 'domcontentloaded',
    timeout: SITE_TIMEOUT_MS,
  });
  await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), {
    timeout: STEP_TIMEOUT_MS,
  });
  await page.evaluate(() => {
    window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false);
  });

  return {
    page,
    consoleErrors,
    pageErrors,
  };
}

async function importFixture(page) {
  const input = await page.waitForSelector('input[type="file"]', {
    timeout: STEP_TIMEOUT_MS,
  });
  await input.uploadFile(FIXTURE_PATH);
  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.();
      return (
        snapshot?.selectedFile?.name === 'laikago_description/urdf/laikago.urdf' &&
        snapshot?.store?.name === 'laikago'
      );
    },
    { timeout: STEP_TIMEOUT_MS },
  );
  await delay(1_000);
}

async function openSourceEditor(page) {
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('button')].some((candidate) =>
        /source code/i.test(candidate.textContent?.trim() ?? ''),
      ),
    { timeout: STEP_TIMEOUT_MS },
  );

  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((candidate) =>
      /source code/i.test(candidate.textContent?.trim() ?? ''),
    );
    if (!(button instanceof HTMLButtonElement)) {
      throw new Error('Source Code button not found');
    }
    button.click();
  });

  await page.waitForFunction(() => (window.monaco?.editor?.getModels?.().length ?? 0) > 0, {
    timeout: STEP_TIMEOUT_MS,
  });
}

async function closeSourceEditor(page) {
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((candidate) => {
      const text = candidate.textContent?.trim() ?? '';
      return text === 'Close' || text === '关闭';
    });
    if (button instanceof HTMLButtonElement) {
      button.click();
    }
  });
}

async function getEditorCode(page) {
  return await page.evaluate(() => window.monaco.editor.getModels()[0]?.getValue() ?? '');
}

async function replaceFirst(page, fromText, toText) {
  await page.evaluate(
    ({ from, to }) => {
      const monaco = window.monaco;
      const model = monaco.editor.getModels()[0];
      const editor = monaco.editor.getEditors()[0];
      const offset = model.getValue().indexOf(from);
      if (offset < 0) {
        throw new Error(`Target text not found: ${from}`);
      }

      const start = model.getPositionAt(offset);
      const end = model.getPositionAt(offset + from.length);
      editor.executeEdits('regression', [
        {
          range: new monaco.Range(start.lineNumber, start.column, end.lineNumber, end.column),
          text: to,
        },
      ]);
    },
    { from: fromText, to: toText },
  );
}

async function clickSave(page) {
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((candidate) => {
      const label = candidate.textContent?.trim().toLowerCase();
      return label === 'save' || label === '保存';
    });
    if (!(button instanceof HTMLButtonElement)) {
      throw new Error('Save button not found');
    }
    button.click();
  });
}

async function readSaveState(page) {
  return await page.evaluate(() => {
    const saveButton = [...document.querySelectorAll('button')].find((candidate) => {
      const label = candidate.textContent?.trim().toLowerCase();
      return label === 'save' || label === '保存';
    });
    const modified = [...document.querySelectorAll('*')].some((node) => {
      const text = node.textContent?.trim();
      return text === 'MODIFIED' || text === 'Modified' || text === '已修改';
    });

    return {
      disabled: saveButton instanceof HTMLButtonElement ? saveButton.disabled : null,
      modified,
    };
  });
}

async function readRobotState(page) {
  return await page.evaluate(() => {
    const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
    const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
    const frFoot = (snapshot?.store?.links ?? []).find((link) => link.name === 'FR_foot') ?? null;
    const runtimeVisual = (runtime?.visualMeshes ?? []).find((mesh) => mesh.link === 'FR_foot');

    return {
      selectedFile: snapshot?.selectedFile?.name ?? null,
      storeRadius: frFoot?.visual?.dimensions?.x ?? null,
      runtimeScale: runtimeVisual?.scale?.[0] ?? null,
    };
  });
}

async function runScenario(page, { autoApply, nextRadius }) {
  await setAutoApplyPreference(page, autoApply);
  await page.reload({
    waitUntil: 'domcontentloaded',
    timeout: SITE_TIMEOUT_MS,
  });
  await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), {
    timeout: STEP_TIMEOUT_MS,
  });
  await page.evaluate(() => {
    window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false);
  });

  await importFixture(page);
  await openSourceEditor(page);

  const initialCode = await getEditorCode(page);
  const initialState = await readRobotState(page);

  await replaceFirst(page, 'radius="0.0165"', `radius="${nextRadius}"`);
  await delay(500);

  const pendingState = {
    save: await readSaveState(page),
    robot: await readRobotState(page),
  };

  if (!autoApply) {
    await clickSave(page);
  }

  await page.waitForFunction(
    (expectedRadius) => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.();
      const frFoot = (snapshot?.store?.links ?? []).find((link) => link.name === 'FR_foot');
      return Math.abs((frFoot?.visual?.dimensions?.x ?? 0) - expectedRadius) < 1e-6;
    },
    { timeout: STEP_TIMEOUT_MS },
    Number(nextRadius),
  );
  await page.waitForFunction(
    (expectedRadius) => {
      const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.();
      const mesh = (runtime?.visualMeshes ?? []).find((entry) => entry.link === 'FR_foot');
      return Math.abs((mesh?.scale?.[0] ?? 0) - expectedRadius) < 1e-6;
    },
    { timeout: STEP_TIMEOUT_MS },
    Number(nextRadius),
  );

  const appliedState = {
    save: await readSaveState(page),
    robot: await readRobotState(page),
  };

  await closeSourceEditor(page);

  return {
    autoApply,
    initialHasRawFoot: initialCode.includes('<link name="FR_foot">'),
    initialHasPrefixedFoot: initialCode.includes('laikago_FR_foot'),
    initialState,
    pendingState,
    appliedState,
  };
}

function validateScenario(scenario, expectedRadius) {
  if (!scenario.initialHasRawFoot || scenario.initialHasPrefixedFoot) {
    throw new Error('Source editor did not show the raw imported URDF.');
  }

  if (Math.abs((scenario.initialState.storeRadius ?? 0) - 0.0165) > 1e-6) {
    throw new Error('Initial store radius did not match the imported Unitree URDF.');
  }

  if (Math.abs((scenario.initialState.runtimeScale ?? 0) - 0.0165) > 1e-6) {
    throw new Error('Initial runtime radius did not match the imported Unitree URDF.');
  }

  if (!scenario.autoApply) {
    if (
      scenario.pendingState.save.disabled !== false ||
      scenario.pendingState.save.modified !== true
    ) {
      throw new Error('Manual-save scenario did not expose a dirty editable state.');
    }

    if (Math.abs((scenario.pendingState.robot.storeRadius ?? 0) - 0.0165) > 1e-6) {
      throw new Error('Manual-save scenario mutated store state before save.');
    }

    if (Math.abs((scenario.pendingState.robot.runtimeScale ?? 0) - 0.0165) > 1e-6) {
      throw new Error('Manual-save scenario mutated runtime state before save.');
    }
  } else if (
    scenario.appliedState.save.disabled !== true ||
    scenario.appliedState.save.modified !== false
  ) {
    throw new Error('Auto-apply scenario should not leave the editor dirty.');
  }

  if (Math.abs((scenario.appliedState.robot.storeRadius ?? 0) - expectedRadius) > 1e-6) {
    throw new Error('Applied store radius did not match the edited Unitree URDF.');
  }

  if (Math.abs((scenario.appliedState.robot.runtimeScale ?? 0) - expectedRadius) > 1e-6) {
    throw new Error('Applied runtime radius did not match the edited Unitree URDF.');
  }
}

async function main() {
  if (!(await pathExists(FIXTURE_PATH))) {
    throw new Error(`Missing fixture archive: ${FIXTURE_PATH}`);
  }

  const site = await ensureSite();
  const browser = await puppeteer.launch({ headless: 'new' });

  try {
    const { page, consoleErrors, pageErrors } = await openPage(browser);

    const manualScenario = await runScenario(page, {
      autoApply: false,
      nextRadius: '0.03',
    });
    const autoScenario = await runScenario(page, {
      autoApply: true,
      nextRadius: '0.031',
    });

    validateScenario(manualScenario, 0.03);
    validateScenario(autoScenario, 0.031);

    const report = {
      generatedAt: new Date().toISOString(),
      manualScenario,
      autoScenario,
      consoleErrors,
      pageErrors,
    };

    await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
    await writeFile(OUTPUT_PATH, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } finally {
    await browser.close();
    await site.stop();
  }
}

await main();

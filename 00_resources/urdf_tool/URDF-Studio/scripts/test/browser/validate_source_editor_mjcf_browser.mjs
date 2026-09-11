#!/usr/bin/env node

import { access, mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

import puppeteer from 'puppeteer';

const SITE_BASE_URL = 'http://127.0.0.1:4173';
const SITE_URL = `${SITE_BASE_URL}/?regressionDebug=1`;
const OUTPUT_PATH = path.resolve('tmp/regression/source-editor-mjcf-browser.json');
const FIXTURE_PATH = path.resolve('tmp/source-editor-mjcf-patch-demo.xml');
const SITE_TIMEOUT_MS = 120_000;
const STEP_TIMEOUT_MS = 30_000;

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
  const consoleWarnings = [];
  const pageErrors = [];

  page.on('console', (message) => {
    const type = String(message.type() || '').toLowerCase();
    if (type === 'error') {
      consoleErrors.push({
        text: message.text(),
        location: message.location(),
      });
      return;
    }

    if (type === 'warn' || type === 'warning') {
      consoleWarnings.push({
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
    consoleWarnings,
    pageErrors,
  };
}

async function resetWorkspace(page) {
  await page.goto(SITE_URL, {
    waitUntil: 'domcontentloaded',
    timeout: STEP_TIMEOUT_MS,
  });
  await page.waitForFunction(() => Boolean(window.__URDF_STUDIO_DEBUG__), {
    timeout: STEP_TIMEOUT_MS,
  });
  await page.evaluate(() => {
    window.__URDF_STUDIO_DEBUG__?.setBeforeUnloadPromptEnabled?.(false);
  });
}

async function importFixture(page) {
  const fileInput = await page.waitForSelector('input[type="file"]', {
    timeout: STEP_TIMEOUT_MS,
  });
  await fileInput.uploadFile(FIXTURE_PATH);

  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.();
      return snapshot?.selectedFile?.name === 'source-editor-mjcf-patch-demo.xml';
    },
    { timeout: STEP_TIMEOUT_MS },
  );
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

  await page.waitForFunction(
    () =>
      Boolean(window.monaco?.editor?.getModels?.().length) &&
      [...document.querySelectorAll('*')].some((node) => node.textContent?.trim() === 'MJCF/XML'),
    { timeout: STEP_TIMEOUT_MS },
  );
}

async function replaceInEditor(page, fromText, toText) {
  await page.evaluate(
    ({ from, to }) => {
      const monaco = window.monaco;
      const model = monaco?.editor?.getModels?.()[0];
      if (!model) {
        throw new Error('Monaco model not found');
      }

      const offset = model.getValue().indexOf(from);
      if (offset < 0) {
        throw new Error(`Target text not found: ${from}`);
      }

      const start = model.getPositionAt(offset);
      const end = model.getPositionAt(offset + from.length);
      const editors = monaco.editor.getEditors?.() ?? [];
      const editor = editors[0] ?? null;

      if (
        !editor ||
        typeof editor.focus !== 'function' ||
        typeof editor.setSelection !== 'function'
      ) {
        throw new Error('Monaco editor instance not available');
      }

      editor.focus();
      editor.setSelection(
        new monaco.Selection(start.lineNumber, start.column, end.lineNumber, end.column),
      );
    },
    { from: fromText, to: toText },
  );

  await page.keyboard.type(toText);
}

async function clickSave(page) {
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((candidate) => {
      const label = candidate.textContent?.trim().toLowerCase();
      return label === 'save';
    });
    if (!(button instanceof HTMLButtonElement)) {
      throw new Error('Save button not found');
    }
    button.click();
  });
}

async function readEditorState(page) {
  return await page.evaluate(() => {
    const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
    const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
    const joints = Object.values(snapshot?.store?.joints ?? {});
    const footJoint = joints.find((joint) => joint && joint.name === 'foot_joint') ?? null;
    const runtimeLinks = Object.values(runtime?.links ?? {});
    const runtimeFoot = runtimeLinks.find((link) => link && link.name === 'foot_link') ?? null;
    const saveButton = [...document.querySelectorAll('button')].find((candidate) => {
      const label = candidate.textContent?.trim().toLowerCase();
      return label === 'save';
    });
    const dirtyBadgeVisible = [...document.querySelectorAll('*')].some(
      (node) => node.textContent?.trim().toLowerCase() === 'modified',
    );
    const modelValue = window.monaco?.editor?.getModels?.()[0]?.getValue?.() ?? null;

    return {
      selectedFile: snapshot?.selectedFile
        ? {
            name: snapshot.selectedFile.name,
            format: snapshot.selectedFile.format,
          }
        : null,
      footJointOriginZ: footJoint?.origin?.xyz?.z ?? null,
      runtimeFootPositionZ: Array.isArray(runtimeFoot?.position) ? runtimeFoot.position[2] : null,
      saveDisabled: saveButton instanceof HTMLButtonElement ? saveButton.disabled : null,
      dirtyBadgeVisible,
      modelValue,
    };
  });
}

function assertClose(actual, expected, label) {
  if (!Number.isFinite(actual) || Math.abs(actual - expected) > 1e-6) {
    throw new Error(`${label} expected ${expected}, received ${actual}`);
  }
}

async function verifyAutoApply(page) {
  await resetWorkspace(page);
  await setAutoApplyPreference(page, true);
  await resetWorkspace(page);
  await importFixture(page);
  await openSourceEditor(page);

  const before = await readEditorState(page);
  assertClose(before.footJointOriginZ, 0.15, 'auto-apply baseline joint origin');
  assertClose(before.runtimeFootPositionZ, 0.25, 'auto-apply baseline runtime z');

  await replaceInEditor(page, 'pos="0 0 0.15"', 'pos="0 0 0.25"');
  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
      const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
      const joints = Object.values(snapshot?.store?.joints ?? {});
      const footJoint = joints.find((joint) => joint && joint.name === 'foot_joint') ?? null;
      const runtimeLinks = Object.values(runtime?.links ?? {});
      const runtimeFoot = runtimeLinks.find((link) => link && link.name === 'foot_link') ?? null;
      const saveButton = [...document.querySelectorAll('button')].find(
        (candidate) => candidate.textContent?.trim().toLowerCase() === 'save',
      );
      const dirtyBadgeVisible = [...document.querySelectorAll('*')].some(
        (node) => node.textContent?.trim().toLowerCase() === 'modified',
      );

      return (
        footJoint?.origin?.xyz?.z === 0.25 &&
        Array.isArray(runtimeFoot?.position) &&
        Math.abs(runtimeFoot.position[2] - 0.5) < 1e-6 &&
        saveButton instanceof HTMLButtonElement &&
        saveButton.disabled === true &&
        dirtyBadgeVisible === false
      );
    },
    { timeout: STEP_TIMEOUT_MS },
  );

  return {
    before,
    after: await readEditorState(page),
  };
}

async function verifyManualSave(page) {
  await resetWorkspace(page);
  await setAutoApplyPreference(page, false);
  await resetWorkspace(page);
  await importFixture(page);
  await openSourceEditor(page);

  const before = await readEditorState(page);
  assertClose(before.footJointOriginZ, 0.15, 'manual baseline joint origin');
  assertClose(before.runtimeFootPositionZ, 0.25, 'manual baseline runtime z');

  await replaceInEditor(page, 'pos="0 0 0.15"', 'pos="0 0 0.35"');
  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
      const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
      const joints = Object.values(snapshot?.store?.joints ?? {});
      const footJoint = joints.find((joint) => joint && joint.name === 'foot_joint') ?? null;
      const runtimeLinks = Object.values(runtime?.links ?? {});
      const runtimeFoot = runtimeLinks.find((link) => link && link.name === 'foot_link') ?? null;
      const saveButton = [...document.querySelectorAll('button')].find(
        (candidate) => candidate.textContent?.trim().toLowerCase() === 'save',
      );
      const dirtyBadgeVisible = [...document.querySelectorAll('*')].some(
        (node) => node.textContent?.trim().toLowerCase() === 'modified',
      );

      return (
        footJoint?.origin?.xyz?.z === 0.15 &&
        Array.isArray(runtimeFoot?.position) &&
        Math.abs(runtimeFoot.position[2] - 0.25) < 1e-6 &&
        saveButton instanceof HTMLButtonElement &&
        saveButton.disabled === false &&
        dirtyBadgeVisible === true
      );
    },
    { timeout: STEP_TIMEOUT_MS },
  );

  const beforeSave = await readEditorState(page);
  await clickSave(page);
  await page.waitForFunction(
    () => {
      const snapshot = window.__URDF_STUDIO_DEBUG__?.getRegressionSnapshot?.() ?? null;
      const runtime = window.__URDF_STUDIO_DEBUG__?.getRuntimeSceneTransforms?.() ?? null;
      const joints = Object.values(snapshot?.store?.joints ?? {});
      const footJoint = joints.find((joint) => joint && joint.name === 'foot_joint') ?? null;
      const runtimeLinks = Object.values(runtime?.links ?? {});
      const runtimeFoot = runtimeLinks.find((link) => link && link.name === 'foot_link') ?? null;
      const saveButton = [...document.querySelectorAll('button')].find(
        (candidate) => candidate.textContent?.trim().toLowerCase() === 'save',
      );
      const dirtyBadgeVisible = [...document.querySelectorAll('*')].some(
        (node) => node.textContent?.trim().toLowerCase() === 'modified',
      );

      return (
        footJoint?.origin?.xyz?.z === 0.35 &&
        Array.isArray(runtimeFoot?.position) &&
        Math.abs(runtimeFoot.position[2] - 0.6) < 1e-6 &&
        saveButton instanceof HTMLButtonElement &&
        saveButton.disabled === true &&
        dirtyBadgeVisible === false
      );
    },
    { timeout: STEP_TIMEOUT_MS },
  );

  return {
    before,
    beforeSave,
    after: await readEditorState(page),
  };
}

async function main() {
  if (!(await pathExists(FIXTURE_PATH))) {
    throw new Error(`Missing MJCF fixture: ${FIXTURE_PATH}`);
  }

  const site = await ensureSite();
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    protocolTimeout: 120_000,
  });

  try {
    const { page, consoleErrors, consoleWarnings, pageErrors } = await openPage(browser);
    const autoApply = await verifyAutoApply(page);
    const manualSave = await verifyManualSave(page);
    const report = {
      ok: true,
      fixturePath: FIXTURE_PATH,
      siteUrl: SITE_URL,
      autoApply,
      manualSave,
      consoleErrors,
      consoleWarnings,
      pageErrors,
    };

    await mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
    await writeFile(OUTPUT_PATH, `${JSON.stringify(report, null, 2)}\n`, 'utf8');

    if (consoleErrors.length > 0 || pageErrors.length > 0) {
      throw new Error('Browser regression encountered console/page errors');
    }

    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  } finally {
    await browser.close();
    await site.stop();
  }
}

main().catch((error) => {
  process.stderr.write(
    `${error instanceof Error ? (error.stack ?? error.message) : String(error)}\n`,
  );
  process.exitCode = 1;
});

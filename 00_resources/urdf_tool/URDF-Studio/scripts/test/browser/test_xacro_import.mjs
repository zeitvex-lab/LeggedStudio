#!/usr/bin/env node

/**
 * Xacro Import browser regression test.
 *
 * Verifies xacro file upload and expansion to URDF.
 */

import {
  createSession, createTestSuite, assert, assertEqual, assertGreaterThan,
  importModel, waitForReady, getTopology, openSourceEditor, getSourceEditorText, store,
  writeReport, printSummary,
} from './helpers/xacro-helpers.mjs';

import path from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';

const MODELS = [
  { xacroPath: 'a1_description/xacro/robot.xacro', expectedName: 'robot.xacro' },
];

async function readSelectedSourceState(page) {
  return page.evaluate(() => {
    const assets = window.__URDF_STUDIO_DEBUG__?.__assetsStore__?.getState?.() ?? null;
    const selectedFile = assets?.selectedFile ?? null;
    const allFileContents = assets?.allFileContents ?? {};
    const selectedAvailableFile = assets?.availableFiles?.find?.(
      (file) => file?.name === selectedFile?.name,
    ) ?? null;

    return {
      fileName: selectedFile?.name ?? null,
      format: selectedFile?.format ?? null,
      selectedContent: selectedFile?.content ?? '',
      availableContent: selectedAvailableFile?.content ?? '',
      allFileContent: selectedFile?.name ? (allFileContents[selectedFile.name] ?? '') : '',
    };
  });
}

async function waitForSelectedSourceText(page, expectedText, timeout = 10_000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    const sourceState = await readSelectedSourceState(page);
    if (sourceState.selectedContent.includes(expectedText)) {
      return sourceState;
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for selected Xacro source text: ${expectedText}`);
}

async function main() {
  const suite = createTestSuite('Xacro Import');
  const session = await createSession();
  const results = [];

  try {
    for (const { xacroPath, expectedName } of MODELS) {
      console.log(`\n── ${xacroPath} ──`);

      try {
        const loadedName = await importModel(session.page, xacroPath, expectedName);
        await waitForReady(session.page);
        const topo = await getTopology(session.page);

        assertGreaterThan(suite, topo.linkCount, 0, `${xacroPath}: links > 0 (${topo.linkCount})`);
        assertGreaterThan(suite, topo.jointCount, 0, `${xacroPath}: joints > 0 (${topo.jointCount})`);

        const loadState = await session.page.evaluate(() =>
          window.__URDF_STUDIO_DEBUG__?.getDocumentLoadState?.());
        assert(suite, loadState?.fileName === loadedName, `${xacroPath}: document state tracks loaded file`);

        await openSourceEditor(session.page);
        const sourceBeforeRename = await readSelectedSourceState(session.page);
        assertEqual(suite, sourceBeforeRename.format, 'xacro', `${xacroPath}: selected source is Xacro`);
        assert(
          suite,
          sourceBeforeRename.selectedContent.includes('<robot name="a1"'),
          `${xacroPath}: raw Xacro source contains robot root`,
        );
        assert(
          suite,
          sourceBeforeRename.selectedContent.includes('<xacro:include'),
          `${xacroPath}: raw Xacro source preserves include directives`,
        );

        await store.setName(session.page, 'a1_source_patch_regression');
        const sourceAfterRename = await waitForSelectedSourceText(
          session.page,
          '<robot name="a1_source_patch_regression"',
        );
        const renamedTopo = await getTopology(session.page);
        assertEqual(
          suite,
          renamedTopo.name,
          'a1_source_patch_regression',
          `${xacroPath}: robot state rename applied`,
        );
        assertEqual(
          suite,
          sourceAfterRename.selectedContent.length - sourceBeforeRename.selectedContent.length,
          'a1_source_patch_regression'.length - 'a1'.length,
          `${xacroPath}: Xacro source rename only changes the root name text`,
        );
        assert(
          suite,
          sourceAfterRename.selectedContent.includes('<xacro:include'),
          `${xacroPath}: patched Xacro source preserves include directives`,
        );
        const editorTextAfterRename = await getSourceEditorText(session.page);
        assert(
          suite,
          editorTextAfterRename.includes('<xacro:include'),
          `${xacroPath}: source editor remains on patched raw Xacro, not generated URDF`,
        );
        assert(
          suite,
          sourceAfterRename.availableContent.includes('<robot name="a1_source_patch_regression"'),
          `${xacroPath}: availableFiles Xacro source reflects robot-state edits`,
        );
        assert(
          suite,
          sourceAfterRename.allFileContent.includes('<robot name="a1_source_patch_regression"'),
          `${xacroPath}: allFileContents Xacro source reflects robot-state edits`,
        );

        results.push({ model: xacroPath, status: 'ok', linkCount: topo.linkCount, jointCount: topo.jointCount });
      } catch (err) {
        assert(suite, false, `${xacroPath}: import succeeded — ${err.message}`);
        results.push({ model: xacroPath, status: 'error', error: err.message });
      }
    }

    const errs = session.errors();
    assert(suite, errs.page.length === 0, `no page errors (${errs.page.length})`);
  } finally {
    await session.cleanup();
  }

  await writeReport('xacro_import', { results });
  process.exitCode = printSummary(suite) ? 0 : 1;
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

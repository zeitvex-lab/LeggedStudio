import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildUsdRoundtripDownloadName,
  exportUsdStageSnapshot,
  getUsdStageExportHandler,
} from './usdStageExport.ts';

test('prefers the explicit USD output file name when building the download name', () => {
  assert.equal(
    buildUsdRoundtripDownloadName('/robots/go2/go2.usd', 'go2.viewer_roundtrip.usd'),
    'go2.viewer_roundtrip.usd',
  );
});

test('falls back to a stage-derived roundtrip USD file name', () => {
  assert.equal(
    buildUsdRoundtripDownloadName('/robots/go2/go2.usda'),
    'go2.viewer_roundtrip.usda',
  );
});

test('resolves the global export handler before renderInterface fallback', async () => {
  const exportLoadedStageSnapshot = async () => ({ ok: true, content: '#usda 1.0' });
  const renderInterfaceExport = async () => ({ ok: true, content: '#usda 1.0', outputFileName: 'from-render-interface.usd' });

  const handler = getUsdStageExportHandler({
    exportLoadedStageSnapshot,
    renderInterface: {
      exportLoadedStageSnapshot: renderInterfaceExport,
    },
  });

  assert.ok(handler);
  assert.deepEqual(handler ? await handler() : null, { ok: true, content: '#usda 1.0' });
});

test('exports a USD stage snapshot without persisting to the server', async () => {
  let receivedOptions: Record<string, unknown> | null = null as Record<string, unknown> | null;
  const payload = await exportUsdStageSnapshot({
    stageSourcePath: '/robots/go2/go2.usd',
    targetWindow: {
      exportLoadedStageSnapshot: async (options) => {
        receivedOptions = options || null;
        return {
          ok: true,
          content: '#usda 1.0\n',
          outputFileName: 'go2.viewer_roundtrip.usd',
        };
      },
    },
  });

  assert.deepEqual(receivedOptions, {
    persistToServer: false,
    overwrite: true,
    flattenStage: false,
    stageSourcePath: '/robots/go2/go2.usd',
    outputFileName: undefined,
  });
  assert.equal(payload.content, '#usda 1.0\n');
  assert.equal(payload.downloadFileName, 'go2.viewer_roundtrip.usd');
});

test('passes persistToServer through to the export bridge when requested', async () => {
  let receivedOptions: Record<string, unknown> | null = null as Record<string, unknown> | null;

  await exportUsdStageSnapshot({
    stageSourcePath: '/robots/go2/go2.usd',
    persistToServer: true,
    targetWindow: {
      exportLoadedStageSnapshot: async (options) => {
        receivedOptions = options || null;
        return {
          ok: true,
          content: '#usda 1.0\n',
          outputFileName: 'go2.viewer_roundtrip.usd',
          outputVirtualPath: '/robots/go2/go2.viewer_roundtrip.usd',
        };
      },
    },
  });

  assert.equal(receivedOptions?.persistToServer, true);
  assert.equal(receivedOptions?.stageSourcePath, '/robots/go2/go2.usd');
});

test('normalizes bare stage source paths before invoking the export bridge', async () => {
  let receivedOptions: Record<string, unknown> | null = null as Record<string, unknown> | null;

  await exportUsdStageSnapshot({
    stageSourcePath: 'robots/b2/b2.usd',
    targetWindow: {
      exportLoadedStageSnapshot: async (options) => {
        receivedOptions = options || null;
        return {
          ok: true,
          content: '#usda 1.0\n',
          outputFileName: 'b2.viewer_roundtrip.usd',
        };
      },
    },
  });

  assert.equal(receivedOptions?.stageSourcePath, '/robots/b2/b2.usd');
});

test('throws an export-unavailable error when no USD export bridge is registered', async () => {
  await assert.rejects(
    () => exportUsdStageSnapshot({ targetWindow: {} }),
    /export-unavailable/,
  );
});

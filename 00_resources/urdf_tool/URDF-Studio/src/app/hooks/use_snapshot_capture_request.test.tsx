import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import {
  createSnapshotCaptureAbortError,
  DEFAULT_SNAPSHOT_CAPTURE_OPTIONS,
  type SnapshotCaptureAction,
  type SnapshotCaptureProgress,
} from '@/shared/components/3d';
import { useSnapshotCaptureRequest } from './use_snapshot_capture_request';

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

test('useSnapshotCaptureRequest aborts the active export without showing a failure toast', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const liveCaptureActionRef: { current: SnapshotCaptureAction | null } = { current: null };
  const frozenPreviewCaptureActionRef: { current: SnapshotCaptureAction | null } = {
    current: null,
  };
  const toastMessages: string[] = [];
  const stateSnapshots: Array<{
    isCapturing: boolean;
    progress: SnapshotCaptureProgress | null;
  }> = [];
  let latestHook: ReturnType<typeof useSnapshotCaptureRequest> | null = null;
  let observedSignal: AbortSignal | null = null;
  let capturePromise: Promise<void> | null = null;

  liveCaptureActionRef.current = async (options) => {
    observedSignal = options?.signal ?? null;
    options?.onProgress?.({ phase: 'rendering', progress: 0.4 });

    await new Promise<void>((_resolve, reject) => {
      options?.signal?.addEventListener(
        'abort',
        () => {
          reject(createSnapshotCaptureAbortError());
        },
        { once: true },
      );
    });
  };

  function Harness() {
    const [isCapturing, setIsCapturing] = useState(false);
    const [progress, setProgress] = useState<SnapshotCaptureProgress | null>(null);
    const hook = useSnapshotCaptureRequest({
      liveCaptureActionRef,
      frozenPreviewCaptureActionRef,
      snapshotPreviewSession: null,
      setIsSnapshotCapturing: setIsCapturing,
      setSnapshotCaptureProgress: setProgress,
      showToast: (message) => {
        toastMessages.push(message);
      },
      snapshotFailedMessage: 'Snapshot failed',
    });

    latestHook = hook;
    useEffect(() => {
      stateSnapshots.push({ isCapturing, progress });
    }, [isCapturing, progress]);

    return null;
  }

  try {
    await act(async () => {
      root.render(React.createElement(Harness));
    });
    assert.ok(latestHook, 'hook should be exposed by the harness');

    await act(async () => {
      capturePromise = latestHook!.handleCaptureSnapshot(DEFAULT_SNAPSHOT_CAPTURE_OPTIONS);
      await Promise.resolve();
    });

    const signalBeforeCancel = observedSignal as AbortSignal | null;
    assert.equal(signalBeforeCancel?.aborted, false);
    assert.deepEqual(stateSnapshots.at(-1), {
      isCapturing: true,
      progress: { phase: 'rendering', progress: 0.4 },
    });

    const pendingCapturePromise = capturePromise;
    assert.ok(pendingCapturePromise, 'capture promise should be pending before cancel');
    await act(async () => {
      latestHook!.handleCancelSnapshotCapture();
      await pendingCapturePromise;
    });

    const signalAfterCancel = observedSignal as AbortSignal | null;
    assert.equal(signalAfterCancel?.aborted, true);
    assert.deepEqual(stateSnapshots.at(-1), {
      isCapturing: false,
      progress: null,
    });
    assert.deepEqual(toastMessages, []);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

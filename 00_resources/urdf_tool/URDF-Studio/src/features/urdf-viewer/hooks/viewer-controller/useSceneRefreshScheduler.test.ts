import test from 'node:test';
import assert from 'node:assert/strict';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import {
  type SceneRefreshOptions,
  useSceneRefreshScheduler,
} from './useSceneRefreshScheduler.ts';

type HookValue = ReturnType<typeof useSceneRefreshScheduler>;

function installDom() {
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  const previousRequestAnimationFrame = Object.getOwnPropertyDescriptor(
    globalThis,
    'requestAnimationFrame',
  );
  const previousCancelAnimationFrame = Object.getOwnPropertyDescriptor(
    globalThis,
    'cancelAnimationFrame',
  );
  const previousReactActEnvironment = Object.getOwnPropertyDescriptor(
    globalThis,
    'IS_REACT_ACT_ENVIRONMENT',
  );
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });
  const callbacks = new Map<number, FrameRequestCallback>();
  let nextFrameHandle = 1;

  const requestFrame = (callback: FrameRequestCallback): number => {
    const handle = nextFrameHandle;
    nextFrameHandle += 1;
    callbacks.set(handle, callback);
    return handle;
  };

  const cancelFrame = (handle: number): void => {
    callbacks.delete(handle);
  };

  Object.defineProperty(dom.window, 'requestAnimationFrame', {
    value: requestFrame,
    configurable: true,
  });
  Object.defineProperty(dom.window, 'cancelAnimationFrame', {
    value: cancelFrame,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'window', {
    value: dom.window,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'document', {
    value: dom.window.document,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'requestAnimationFrame', {
    value: requestFrame,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'cancelAnimationFrame', {
    value: cancelFrame,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
    value: true,
    configurable: true,
  });

  return {
    dom,
    scheduledFrameCount: () => callbacks.size,
    flushNextFrame: () => {
      const entry = callbacks.entries().next();
      if (entry.done) {
        return false;
      }
      const [handle, callback] = entry.value;
      callbacks.delete(handle);
      callback(0);
      return true;
    },
    restoreGlobals: () => {
      restoreGlobalProperty('window', previousWindow);
      restoreGlobalProperty('document', previousDocument);
      restoreGlobalProperty('requestAnimationFrame', previousRequestAnimationFrame);
      restoreGlobalProperty('cancelAnimationFrame', previousCancelAnimationFrame);
      restoreGlobalProperty('IS_REACT_ACT_ENVIRONMENT', previousReactActEnvironment);
    },
  };
}

function restoreGlobalProperty(
  key:
    | 'window'
    | 'document'
    | 'requestAnimationFrame'
    | 'cancelAnimationFrame'
    | 'IS_REACT_ACT_ENVIRONMENT',
  descriptor: PropertyDescriptor | undefined,
): void {
  if (descriptor) {
    Object.defineProperty(globalThis, key, descriptor);
    return;
  }

  Reflect.deleteProperty(globalThis, key);
}

async function renderScheduler() {
  const env = installDom();
  const container = env.dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);
  let hookValue: HookValue | null = null as HookValue | null;

  function Probe() {
    hookValue = useSceneRefreshScheduler();
    return null;
  }

  await act(async () => {
    root.render(React.createElement(Probe));
  });

  const getHook = () => {
    assert.ok(hookValue, 'hook should render');
    return hookValue;
  };

  return { ...env, root, getHook };
}

async function cleanup(root: Root, dom: JSDOM, restoreGlobals: () => void) {
  await act(async () => {
    root.unmount();
  });
  dom.window.close();
  restoreGlobals();
}

test('useSceneRefreshScheduler coalesces same-frame refreshes and preserves force', async () => {
  const { dom, root, getHook, scheduledFrameCount, flushNextFrame, restoreGlobals } =
    await renderScheduler();
  const refreshCalls: Array<SceneRefreshOptions | undefined> = [];

  try {
    await act(async () => {
      getHook().registerSceneRefresh((options) => {
        refreshCalls.push(options);
      });
      getHook().requestSceneRefresh();
      getHook().requestSceneRefresh({ force: true });
      getHook().requestSceneRefresh();
    });

    assert.equal(scheduledFrameCount(), 1);
    assert.deepEqual(refreshCalls, []);

    await act(async () => {
      assert.equal(flushNextFrame(), true);
    });

    assert.deepEqual(refreshCalls, [{ force: true }]);
    assert.equal(scheduledFrameCount(), 0);
  } finally {
    await cleanup(root, dom, restoreGlobals);
  }
});

test('useSceneRefreshScheduler cancels pending refresh on unmount', async () => {
  const { dom, root, getHook, scheduledFrameCount, flushNextFrame, restoreGlobals } =
    await renderScheduler();
  const refreshCalls: Array<SceneRefreshOptions | undefined> = [];

  getHook().registerSceneRefresh((options) => {
    refreshCalls.push(options);
  });
  getHook().requestSceneRefresh({ force: true });

  assert.equal(scheduledFrameCount(), 1);

  await cleanup(root, dom, restoreGlobals);

  assert.equal(scheduledFrameCount(), 0);
  assert.equal(flushNextFrame(), false);
  assert.deepEqual(refreshCalls, []);
});

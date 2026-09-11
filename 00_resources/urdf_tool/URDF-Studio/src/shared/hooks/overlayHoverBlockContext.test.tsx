import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';

import { OverlayHoverBlockProvider, useOverlayHoverBlock } from './useOverlayHoverBlock.ts';

function installDom() {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalActEnvironment = (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
    .IS_REACT_ACT_ENVIRONMENT;
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: dom.window,
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: dom.window.document,
  });
  Object.defineProperty(globalThis, 'HTMLElement', {
    configurable: true,
    value: dom.window.HTMLElement,
  });
  Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
    configurable: true,
    value: true,
  });

  return {
    rootElement: dom.window.document.getElementById('root') as HTMLElement,
    restore() {
      dom.window.close();
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: originalWindow,
      });
      Object.defineProperty(globalThis, 'document', {
        configurable: true,
        value: originalDocument,
      });
      Object.defineProperty(globalThis, 'HTMLElement', {
        configurable: true,
        value: originalHTMLElement,
      });
      Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
        configurable: true,
        value: originalActEnvironment,
      });
    },
  };
}

test('useOverlayHoverBlock uses app-provided hover block actions and cleans up active blocks', async () => {
  const dom = installDom();
  const root = createRoot(dom.rootElement);
  const calls: string[] = [];
  let activateHoverBlock: (() => void) | null = null;

  function Harness() {
    const actions = useOverlayHoverBlock();
    activateHoverBlock = actions.activateHoverBlock;
    return null;
  }

  try {
    await act(async () => {
      root.render(
        <OverlayHoverBlockProvider
          value={{
            beginHoverBlock: () => calls.push('begin'),
            endHoverBlock: () => calls.push('end'),
            clearHover: () => calls.push('clear'),
          }}
        >
          <Harness />
        </OverlayHoverBlockProvider>,
      );
    });

    await act(async () => {
      activateHoverBlock?.();
    });

    await act(async () => {
      root.unmount();
    });

    assert.deepEqual(calls, ['begin', 'clear', 'end']);
  } finally {
    dom.restore();
  }
});

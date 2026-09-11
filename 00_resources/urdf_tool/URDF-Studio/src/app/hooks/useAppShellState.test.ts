import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { useAppShellState } from './useAppShellState.ts';

function restoreGlobalProperty<T extends keyof typeof globalThis>(
  key: T,
  originalValue: (typeof globalThis)[T] | undefined,
) {
  if (originalValue === undefined) {
    delete globalThis[key];
    return;
  }

  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value: originalValue,
  });
}

function installDomEnvironment() {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalNavigator = globalThis.navigator;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalSVGElement = globalThis.SVGElement;
  const originalNode = globalThis.Node;
  const originalMutationObserver = globalThis.MutationObserver;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
  });

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: dom.window,
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    writable: true,
    value: dom.window.document,
  });
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value: dom.window.navigator,
  });
  Object.defineProperty(globalThis, 'HTMLElement', {
    configurable: true,
    writable: true,
    value: dom.window.HTMLElement,
  });
  Object.defineProperty(globalThis, 'SVGElement', {
    configurable: true,
    writable: true,
    value: dom.window.SVGElement,
  });
  Object.defineProperty(globalThis, 'Node', {
    configurable: true,
    writable: true,
    value: dom.window.Node,
  });
  Object.defineProperty(globalThis, 'MutationObserver', {
    configurable: true,
    writable: true,
    value: dom.window.MutationObserver,
  });
  Object.defineProperty(globalThis, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: (callback: FrameRequestCallback) => setTimeout(() => callback(Date.now()), 0),
  });
  Object.defineProperty(globalThis, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: (handle: number) => clearTimeout(handle),
  });

  return {
    restore() {
      dom.window.close();
      restoreGlobalProperty('window', originalWindow);
      restoreGlobalProperty('document', originalDocument);
      restoreGlobalProperty('navigator', originalNavigator);
      restoreGlobalProperty('HTMLElement', originalHTMLElement);
      restoreGlobalProperty('SVGElement', originalSVGElement);
      restoreGlobalProperty('Node', originalNode);
      restoreGlobalProperty('MutationObserver', originalMutationObserver);
      restoreGlobalProperty('requestAnimationFrame', originalRequestAnimationFrame);
      restoreGlobalProperty('cancelAnimationFrame', originalCancelAnimationFrame);
    },
  };
}

function renderHook() {
  let hookValue: ReturnType<typeof useAppShellState> | null = null as ReturnType<typeof useAppShellState> | null;
  const container = document.createElement('div');
  document.body.appendChild(container);

  function Probe() {
    hookValue = useAppShellState();
    return null;
  }

  const root = createRoot(container);
  flushSync(() => {
    root.render(React.createElement(Probe));
  });

  assert.ok(hookValue, 'hook should render');

  return {
    get hook() {
      assert.ok(hookValue, 'hook should stay mounted');
      return hookValue;
    },
    cleanup() {
      flushSync(() => {
        root.unmount();
      });
      if (container.parentNode) {
        container.parentNode.removeChild(container);
      }
    },
  };
}

test('useAppShellState tracks split AI entry points and preserves legacy modal setter behavior', async () => {
  const domEnvironment = installDomEnvironment();
  const rendered = renderHook();

  try {
    assert.equal(rendered.hook.isAIModalOpen, false);
    assert.equal(rendered.hook.isAIInspectionOpen, false);
    assert.equal(rendered.hook.isAIConversationOpen, false);
    assert.equal(rendered.hook.aiLaunchMode, null);

    flushSync(() => {
      rendered.hook.openAIConversation();
    });

    assert.equal(rendered.hook.isAIModalOpen, true);
    assert.equal(rendered.hook.isAIInspectionOpen, false);
    assert.equal(rendered.hook.isAIConversationOpen, true);
    assert.equal(rendered.hook.aiLaunchMode, 'conversation');

    flushSync(() => {
      rendered.hook.openAIInspection();
    });

    assert.equal(rendered.hook.isAIModalOpen, true);
    assert.equal(rendered.hook.isAIInspectionOpen, true);
    assert.equal(rendered.hook.isAIConversationOpen, false);
    assert.equal(rendered.hook.aiLaunchMode, 'inspection');

    flushSync(() => {
      rendered.hook.closeAIEntryPoints();
    });

    assert.equal(rendered.hook.isAIModalOpen, false);
    assert.equal(rendered.hook.isAIInspectionOpen, false);
    assert.equal(rendered.hook.isAIConversationOpen, false);
    assert.equal(rendered.hook.aiLaunchMode, null);

    flushSync(() => {
      rendered.hook.setIsAIModalOpen(true);
    });

    assert.equal(rendered.hook.isAIModalOpen, true);
    assert.equal(rendered.hook.isAIInspectionOpen, true);
    assert.equal(rendered.hook.isAIConversationOpen, false);
    assert.equal(rendered.hook.aiLaunchMode, 'inspection');

    flushSync(() => {
      rendered.hook.setIsAIModalOpen(false);
    });

    assert.equal(rendered.hook.isAIModalOpen, false);
    assert.equal(rendered.hook.isAIInspectionOpen, false);
    assert.equal(rendered.hook.isAIConversationOpen, false);
    assert.equal(rendered.hook.aiLaunchMode, null);
  } finally {
    rendered.cleanup();
    void domEnvironment;
    await new Promise<void>((resolve) => {
      setTimeout(() => resolve(), 0);
    });
  }
});

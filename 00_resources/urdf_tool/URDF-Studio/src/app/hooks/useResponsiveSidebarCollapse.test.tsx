import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { useResponsiveSidebarCollapse } from './useResponsiveSidebarCollapse.ts';

type SidebarState = Parameters<typeof useResponsiveSidebarCollapse>[0]['sidebar'];
type SetSidebar = Parameters<typeof useResponsiveSidebarCollapse>[0]['setSidebar'];

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

function installDomEnvironment(initialWidth: number) {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalNavigator = globalThis.navigator;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalNode = globalThis.Node;
  const originalActEnvironment = (
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
  ).IS_REACT_ACT_ENVIRONMENT;

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
  });

  Object.defineProperty(dom.window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: initialWidth,
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
  Object.defineProperty(globalThis, 'Node', {
    configurable: true,
    writable: true,
    value: dom.window.Node,
  });
  Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
    configurable: true,
    writable: true,
    value: true,
  });

  return {
    setWidth(width: number) {
      Object.defineProperty(dom.window, 'innerWidth', {
        configurable: true,
        writable: true,
        value: width,
      });
    },
    dispatchResize() {
      dom.window.dispatchEvent(new dom.window.Event('resize'));
    },
    restore() {
      dom.window.close();
      restoreGlobalProperty('window', originalWindow);
      restoreGlobalProperty('document', originalDocument);
      restoreGlobalProperty('navigator', originalNavigator);
      restoreGlobalProperty('HTMLElement', originalHTMLElement);
      restoreGlobalProperty('Node', originalNode);
      if (originalActEnvironment === undefined) {
        delete (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT;
      } else {
        Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
          configurable: true,
          writable: true,
          value: originalActEnvironment,
        });
      }
    },
  };
}

async function renderHook(options: {
  sidebar: SidebarState;
  setSidebar: SetSidebar;
}) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  function Probe(props: {
    sidebar: SidebarState;
    setSidebar: SetSidebar;
  }) {
    useResponsiveSidebarCollapse(props);
    return null;
  }

  await act(async () => {
    root.render(React.createElement(Probe, options));
  });

  return {
    async cleanup() {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

test('collapses both sidebars below the compact workspace width', async () => {
  const dom = installDomEnvironment(900);
  const calls: Array<{ side: 'left' | 'right'; collapsed: boolean }> = [];

  try {
    const rendered = await renderHook({
      sidebar: { leftCollapsed: false, rightCollapsed: false },
      setSidebar: (side, collapsed) => {
        calls.push({ side, collapsed });
      },
    });

    assert.deepEqual(calls, [
      { side: 'left', collapsed: true },
      { side: 'right', collapsed: true },
    ]);
    await rendered.cleanup();
  } finally {
    dom.restore();
  }
});

test('collapses only the right sidebar at medium workspace widths', async () => {
  const dom = installDomEnvironment(1100);
  const calls: Array<{ side: 'left' | 'right'; collapsed: boolean }> = [];

  try {
    const rendered = await renderHook({
      sidebar: { leftCollapsed: false, rightCollapsed: false },
      setSidebar: (side, collapsed) => {
        calls.push({ side, collapsed });
      },
    });

    assert.deepEqual(calls, [{ side: 'right', collapsed: true }]);
    await rendered.cleanup();
  } finally {
    dom.restore();
  }
});

test('leaves sidebars unchanged at wide workspace widths', async () => {
  const dom = installDomEnvironment(1200);
  const calls: Array<{ side: 'left' | 'right'; collapsed: boolean }> = [];

  try {
    const rendered = await renderHook({
      sidebar: { leftCollapsed: false, rightCollapsed: false },
      setSidebar: (side, collapsed) => {
        calls.push({ side, collapsed });
      },
    });

    assert.deepEqual(calls, []);
    await rendered.cleanup();
  } finally {
    dom.restore();
  }
});

test('runs the resize policy until cleanup removes the listener', async () => {
  const dom = installDomEnvironment(1400);
  const calls: Array<{ side: 'left' | 'right'; collapsed: boolean }> = [];

  try {
    const rendered = await renderHook({
      sidebar: { leftCollapsed: false, rightCollapsed: false },
      setSidebar: (side, collapsed) => {
        calls.push({ side, collapsed });
      },
    });

    assert.deepEqual(calls, []);

    await act(async () => {
      dom.setWidth(900);
      dom.dispatchResize();
    });

    assert.deepEqual(calls, [
      { side: 'left', collapsed: true },
      { side: 'right', collapsed: true },
    ]);

    await rendered.cleanup();

    await act(async () => {
      dom.dispatchResize();
    });

    assert.deepEqual(calls, [
      { side: 'left', collapsed: true },
      { side: 'right', collapsed: true },
    ]);
  } finally {
    dom.restore();
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { ExportProgressDialog } from './ExportProgressDialog.tsx';

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
  (globalThis as { HTMLInputElement?: typeof HTMLInputElement }).HTMLInputElement = dom.window.HTMLInputElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { PointerEvent?: typeof PointerEvent }).PointerEvent = dom.window.PointerEvent ?? dom.window.MouseEvent;
  (globalThis as { FocusEvent?: typeof FocusEvent }).FocusEvent = dom.window.FocusEvent;
  (globalThis as { KeyboardEvent?: typeof KeyboardEvent }).KeyboardEvent = dom.window.KeyboardEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

function createComponentRoot() {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  return { dom, container, root };
}

async function destroyComponentRoot(dom: JSDOM, root: Root) {
  await act(async () => {
    root.unmount();
  });
  dom.window.close();
}

test('project export progress dialog keeps the full progress card reachable', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await act(async () => {
      root.render(
        React.createElement(ExportProgressDialog, {
          lang: 'zh',
          progress: {
            stepLabel: '打包压缩文件',
            detail: '正在压缩 assets/link_shoulder_v.obj',
            progress: 0.9,
            currentStep: 6,
            totalSteps: 6,
            indeterminate: false,
          },
        }),
      );
    });

    const dialogRoot = container.firstElementChild as HTMLElement | null;
    assert.ok(dialogRoot, 'dialog root should render');
    assert.ok(
      Number.parseFloat(dialogRoot.style.height || '0') >= 520,
      'project export progress dialog should reserve enough height for the full progress card',
    );

    const scrollBody = container.querySelector('.overflow-y-auto');
    assert.ok(scrollBody, 'project export progress dialog should keep the body scrollable when content grows');
    assert.match(container.textContent ?? '', /打包压缩文件/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { PanelSegmentedControl } from './PanelSegmentedControl';

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
  (globalThis as { HTMLButtonElement?: typeof HTMLButtonElement }).HTMLButtonElement =
    dom.window.HTMLButtonElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
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

function renderControl(
  root: Root,
  props: Partial<React.ComponentProps<typeof PanelSegmentedControl<'en' | 'zh'>>> = {},
) {
  return act(async () => {
    root.render(
      React.createElement(PanelSegmentedControl<'en' | 'zh'>, {
        options: [
          { value: 'en', label: 'English' },
          { value: 'zh', label: '中文' },
        ],
        value: 'en',
        onChange: () => {},
        stretch: false,
        ...props,
      }),
    );
  });
}

test('PanelSegmentedControl exposes the shared muted segmented surface and selected ring', async () => {
  const { dom, container, root } = createComponentRoot();
  const changes: Array<'en' | 'zh'> = [];

  try {
    await renderControl(root, {
      onChange: (value) => changes.push(value),
    });

    const group = container.querySelector('div.bg-settings-muted');
    assert.ok(group, 'shared panel segmented control should use the muted panel surface');

    const buttons = Array.from(container.querySelectorAll('button')) as HTMLButtonElement[];
    assert.equal(buttons.length, 2, 'shared panel segmented control should render both options');
    assert.match(buttons[0]?.className ?? '', /\bbg-segmented-active\b/);
    assert.match(buttons[0]?.className ?? '', /\bring-1\b/);
    assert.match(buttons[1]?.className ?? '', /\btext-text-secondary\b/);

    await act(async () => {
      buttons[1]?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.deepEqual(changes, ['zh']);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

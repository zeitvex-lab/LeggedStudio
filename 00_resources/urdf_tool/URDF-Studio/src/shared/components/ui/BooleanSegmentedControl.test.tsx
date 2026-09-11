import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { BooleanSegmentedControl } from './BooleanSegmentedControl';

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
  props: Partial<React.ComponentProps<typeof BooleanSegmentedControl>> = {},
) {
  return act(async () => {
    root.render(
      React.createElement(BooleanSegmentedControl, {
        value: true,
        onChange: () => {},
        trueLabel: 'Yes',
        falseLabel: 'No',
        ariaLabel: 'Import warning',
        ...props,
      }),
    );
  });
}

test('BooleanSegmentedControl exposes a reusable yes/no radiogroup and emits boolean changes', async () => {
  const { dom, container, root } = createComponentRoot();
  const changes: boolean[] = [];

  await renderControl(root, {
    value: true,
    onChange: (nextValue) => changes.push(nextValue),
  });

  const group = container.querySelector('[role="radiogroup"]');
  assert.ok(group, 'boolean control should expose a radiogroup');

  const options = Array.from(container.querySelectorAll('[role="radio"]')) as HTMLButtonElement[];
  assert.equal(options.length, 2, 'boolean control should render exactly two options');
  assert.equal(options[0]?.textContent?.trim(), 'Yes');
  assert.equal(options[0]?.getAttribute('aria-checked'), 'true');
  assert.equal(options[1]?.textContent?.trim(), 'No');
  assert.equal(options[1]?.getAttribute('aria-checked'), 'false');

  await act(async () => {
    options[1]?.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  });

  assert.deepEqual(changes, [false], 'clicking the opposite option should emit the next boolean');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

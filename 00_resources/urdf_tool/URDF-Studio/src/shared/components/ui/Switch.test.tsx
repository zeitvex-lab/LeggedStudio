import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { Switch } from './Switch';

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
  (globalThis as { HTMLSpanElement?: typeof HTMLSpanElement }).HTMLSpanElement =
    dom.window.HTMLSpanElement;
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

function renderControl(root: Root, props: Partial<React.ComponentProps<typeof Switch>> = {}) {
  return act(async () => {
    root.render(
      React.createElement(Switch, {
        checked: true,
        onChange: () => {},
        ariaLabel: 'Import warning',
        ...props,
      }),
    );
  });
}

function SwitchHarness({ initialChecked = true }: { initialChecked?: boolean }) {
  const [checked, setChecked] = React.useState(initialChecked);

  return React.createElement(Switch, {
    checked,
    onChange: setChecked,
    ariaLabel: 'Import warning',
  });
}

test('Switch skips non-interactive checked-state motion', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await renderControl(root, {
      checked: true,
    });

    const toggle = container.querySelector('[role="switch"]') as HTMLButtonElement | null;
    assert.ok(toggle, 'switch should render a toggle button');
    assert.match(
      toggle.className,
      /\btransition-none\b/,
      'initially mounted switches should not animate into their checked state',
    );

    const thumb = toggle.querySelector('span') as HTMLSpanElement | null;
    assert.ok(thumb, 'switch should render a thumb');
    assert.match(
      thumb.className,
      /\btransition-none\b/,
      'the thumb should also skip initial mount animation',
    );

    await renderControl(root, {
      checked: false,
    });

    assert.match(
      toggle.className,
      /\btransition-none\b/,
      'programmatic checked changes should not animate after mount',
    );
    assert.match(
      thumb.className,
      /\btransition-none\b/,
      'programmatic thumb updates should not animate after mount',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('Switch enables transitions after a user toggle', async () => {
  const { dom, container, root } = createComponentRoot();

  try {
    await act(async () => {
      root.render(React.createElement(SwitchHarness));
    });

    const toggle = container.querySelector('[role="switch"]') as HTMLButtonElement | null;
    assert.ok(toggle, 'switch should render a toggle button');
    const thumb = toggle.querySelector('span') as HTMLSpanElement | null;
    assert.ok(thumb, 'switch should render a thumb');

    await act(async () => {
      toggle.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.equal(toggle.getAttribute('aria-checked'), 'false');
    assert.doesNotMatch(
      toggle.className,
      /\btransition-none\b/,
      'user toggles should restore switch transition classes',
    );
    assert.match(
      toggle.className,
      /transition-\[background-color,border-color\]/,
      'background and border color should animate on user toggles',
    );
    assert.doesNotMatch(
      thumb.className,
      /\btransition-none\b/,
      'thumb transitions should also re-enable on user toggles',
    );
    assert.match(thumb.className, /\btransition\b/, 'thumb motion should animate on user toggles');
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('Switch renders labelled toggles as a single interactive target', async () => {
  const { dom, container, root } = createComponentRoot();
  const changes: boolean[] = [];

  try {
    await renderControl(root, {
      checked: false,
      label: 'Show grid',
      ariaLabel: undefined,
      onChange: (checked) => changes.push(checked),
    });

    const buttons = Array.from(container.querySelectorAll('button'));
    assert.equal(buttons.length, 1, 'labelled switches should not render a second label button');

    const toggle = container.querySelector('[role="switch"]') as HTMLButtonElement | null;
    assert.ok(toggle, 'switch should render one switch button');
    assert.equal(toggle.getAttribute('aria-labelledby') != null, true);
    assert.equal(toggle.textContent?.includes('Show grid'), true);

    await act(async () => {
      toggle.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });
    assert.deepEqual(changes, [true]);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

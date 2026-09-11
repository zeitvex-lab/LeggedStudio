import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { Dialog } from './Dialog';

function installDom() {
  const dom = new JSDOM(
    '<!doctype html><html><body><button id="launcher">Open</button><div id="root"></div></body></html>',
    {
      url: 'http://localhost/',
      pretendToBeVisual: true,
    },
  );

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
  (globalThis as { KeyboardEvent?: typeof KeyboardEvent }).KeyboardEvent = dom.window.KeyboardEvent;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

test('Dialog traps keyboard focus and restores focus on close', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  const launcher = dom.window.document.getElementById('launcher');
  assert.ok(container, 'root container should exist');
  assert.ok(launcher instanceof dom.window.HTMLButtonElement);

  launcher.focus();
  const root = createRoot(container);

  function Wrapper() {
    const [isOpen, setIsOpen] = React.useState(true);

    return (
      <Dialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Keyboard dialog"
        closeLabel="Close keyboard dialog"
      >
        <button type="button">First action</button>
        <button type="button">Last action</button>
      </Dialog>
    );
  }

  try {
    await act(async () => {
      root.render(<Wrapper />);
    });

    // The dialog container receives initial focus (NOT the header close
    // button), so an in-flight Enter keyup that opened the dialog cannot
    // immediately activate the close button.
    const dialogEl = dom.window.document.querySelector('[role="dialog"]');
    assert.ok(dialogEl instanceof dom.window.HTMLElement);
    assert.equal(dom.window.document.activeElement, dialogEl);

    const closeButton = Array.from(
      dom.window.document.querySelectorAll('button[aria-label="Close keyboard dialog"]'),
    ).find((button) => button.getAttribute('tabindex') !== '-1');
    assert.ok(closeButton instanceof dom.window.HTMLButtonElement);

    const actionButtons = Array.from(dom.window.document.querySelectorAll('button')).filter(
      (button) => button.textContent?.includes('action'),
    );
    assert.equal(actionButtons.length, 2);
    const firstAction = actionButtons[0];
    const lastAction = actionButtons[1];
    assert.ok(firstAction instanceof dom.window.HTMLButtonElement);
    assert.ok(lastAction instanceof dom.window.HTMLButtonElement);

    closeButton.focus();
    await act(async () => {
      dom.window.document.dispatchEvent(
        new dom.window.KeyboardEvent('keydown', {
          bubbles: true,
          key: 'Tab',
          shiftKey: true,
        }),
      );
    });
    assert.equal(dom.window.document.activeElement, lastAction);

    lastAction.focus();
    await act(async () => {
      dom.window.document.dispatchEvent(
        new dom.window.KeyboardEvent('keydown', {
          bubbles: true,
          key: 'Tab',
        }),
      );
    });
    assert.equal(dom.window.document.activeElement, closeButton);

    await act(async () => {
      dom.window.document.dispatchEvent(
        new dom.window.KeyboardEvent('keydown', {
          bubbles: true,
          key: 'Escape',
        }),
      );
    });

    assert.equal(dom.window.document.querySelector('[role="dialog"]'), null);
    assert.equal(dom.window.document.activeElement, launcher);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

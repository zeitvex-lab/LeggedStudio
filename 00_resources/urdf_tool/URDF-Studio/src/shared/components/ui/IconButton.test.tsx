import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { IconButton } from './IconButton';
import { CLOSE_BUTTON_DANGER_INTERACTION_CLASS } from './closeButtonStyles';

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
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

test('IconButton close variant uses the shared danger hover treatment', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(
        <IconButton variant="close" aria-label="Close">
          x
        </IconButton>,
      );
    });

    const closeButton = container.querySelector<HTMLButtonElement>('button[aria-label="Close"]');
    assert.ok(closeButton, 'close button should render');
    for (const classToken of CLOSE_BUTTON_DANGER_INTERACTION_CLASS.split(' ')) {
      assert.ok(
        closeButton.classList.contains(classToken),
        `close button should include ${classToken}`,
      );
    }
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

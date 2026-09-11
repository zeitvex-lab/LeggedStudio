import test from 'node:test';
import assert from 'node:assert/strict';
import { useCallback } from 'react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { useUsdHighlightLifecycle } from './useUsdHighlightLifecycle.ts';

function createComponentRoot(): {
  dom: JSDOM;
  container: HTMLDivElement;
  root: Root;
} {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  const { window } = dom;
  globalThis.window = window as unknown as typeof globalThis.window;
  globalThis.document = window.document;
  globalThis.HTMLElement = window.HTMLElement;
  globalThis.Node = window.Node;
  Object.defineProperty(globalThis, 'IS_REACT_ACT_ENVIRONMENT', {
    configurable: true,
    writable: true,
    value: true,
  });

  const container = window.document.createElement('div');
  window.document.body.appendChild(container);
  const root = createRoot(container);
  return { dom, container, root };
}

test('rerendering USD highlight sync does not revert highlights before unmount', async () => {
  const { dom, root } = createComponentRoot();
  const lifecycleCalls: string[] = [];

  function Harness({ value }: { value: number }) {
    const syncUsdHighlights = useCallback(() => {
      lifecycleCalls.push(`sync:${value}`);
    }, [value]);

    const revertUsdHighlights = useCallback(() => {
      lifecycleCalls.push('revert');
    }, []);

    useUsdHighlightLifecycle(syncUsdHighlights, revertUsdHighlights);
    return null;
  }

  await act(async () => {
    root.render(<Harness value={1} />);
  });

  assert.deepEqual(lifecycleCalls, ['sync:1']);

  await act(async () => {
    root.render(<Harness value={2} />);
  });

  assert.deepEqual(lifecycleCalls, ['sync:1', 'sync:2']);

  await act(async () => {
    root.unmount();
  });

  assert.deepEqual(lifecycleCalls, ['sync:1', 'sync:2', 'revert']);
  dom.window.close();
});

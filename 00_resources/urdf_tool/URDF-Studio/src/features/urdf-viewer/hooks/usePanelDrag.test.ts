import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act, useLayoutEffect, useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { usePanelDrag } from './usePanelDrag.ts';

function createRect(left: number, top: number, width: number, height: number) {
  return {
    x: left,
    y: top,
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    toJSON() {
      return this;
    },
  };
}

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
  (globalThis as { HTMLDivElement?: typeof HTMLDivElement }).HTMLDivElement = dom.window.HTMLDivElement;
  (globalThis as { HTMLButtonElement?: typeof HTMLButtonElement }).HTMLButtonElement = dom.window.HTMLButtonElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame = dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver = class ResizeObserver {
    observe() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
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

type HarnessStyle = React.CSSProperties & Record<string, string>;

function Harness({ safeAreaStyle }: { safeAreaStyle?: HarnessStyle }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const optionsPanelRef = useRef<HTMLDivElement>(null);
  const jointPanelRef = useRef<HTMLDivElement>(null);
  const measurePanelRef = useRef<HTMLDivElement>(null);
  const paintPanelRef = useRef<HTMLDivElement>(null);
  const drag = usePanelDrag(
    containerRef,
    optionsPanelRef,
    jointPanelRef,
    measurePanelRef,
    paintPanelRef,
  );

  useLayoutEffect(() => {
    const containerElement = containerRef.current;
    const jointPanelElement = jointPanelRef.current;

    if (!containerElement || !jointPanelElement) {
      return;
    }

    const currentPos = drag.jointPanelPos ?? { x: 20, y: 30 };

    Object.defineProperty(containerElement, 'getBoundingClientRect', {
      configurable: true,
      value: () => createRect(0, 0, 600, 400),
    });

    Object.defineProperty(jointPanelElement, 'getBoundingClientRect', {
      configurable: true,
      value: () => createRect(currentPos.x, currentPos.y, 200, 100),
    });
  }, [drag.jointPanelPos]);

  return React.createElement(
    'div',
    {
      ref: containerRef,
      style: safeAreaStyle,
      onMouseMove: drag.handleMouseMove,
      onMouseUp: drag.handleMouseUp,
    },
    React.createElement('div', { ref: jointPanelRef }, [
      React.createElement(
        'button',
        {
          id: 'joint-header',
          key: 'header',
          onMouseDown: (event: React.MouseEvent) => drag.handleMouseDown('joints', event),
        },
        'drag',
      ),
    ]),
    React.createElement(
      'output',
      { id: 'joint-pos' },
      drag.jointPanelPos ? `${drag.jointPanelPos.x},${drag.jointPanelPos.y}` : 'null',
    ),
  );
}

async function renderHarness(root: Root, safeAreaStyle?: HarnessStyle) {
  await act(async () => {
    root.render(React.createElement(Harness, { safeAreaStyle }));
  });
}

test('joint panel dragging keeps updating when the mousemove happens on document', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderHarness(root);

  const header = container.querySelector('#joint-header');
  const jointPanel = header?.parentElement as HTMLDivElement | null;
  const positionOutput = container.querySelector('#joint-pos');
  assert.ok(header, 'joint drag header should render');
  assert.ok(jointPanel, 'joint panel should render');
  assert.ok(positionOutput, 'position output should render');

  assert.equal(positionOutput.textContent, 'null');

  await act(async () => {
    header.dispatchEvent(new dom.window.MouseEvent('mousedown', {
      bubbles: true,
      cancelable: true,
      clientX: 50,
      clientY: 60,
    }));
  });

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousemove', {
      bubbles: true,
      cancelable: true,
      clientX: 170,
      clientY: 190,
      buttons: 1,
    }));
  });

  assert.equal(jointPanel.style.left, '140px');
  assert.equal(jointPanel.style.top, '160px');
  assert.equal(positionOutput.textContent, 'null');

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousemove', {
      bubbles: true,
      cancelable: true,
      clientX: 210,
      clientY: 230,
      buttons: 1,
    }));
  });

  assert.equal(jointPanel.style.left, '180px');
  assert.equal(jointPanel.style.top, '200px');
  assert.equal(positionOutput.textContent, 'null');

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mouseup', {
      bubbles: true,
      cancelable: true,
      clientX: 210,
      clientY: 230,
    }));
  });

  assert.equal(positionOutput.textContent, '180,200');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('joint panel dragging can overflow the viewer while keeping a visible grab area', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderHarness(root);

  const header = container.querySelector('#joint-header');
  const jointPanel = header?.parentElement as HTMLDivElement | null;
  const positionOutput = container.querySelector('#joint-pos');
  assert.ok(header, 'joint drag header should render');
  assert.ok(jointPanel, 'joint panel should render');
  assert.ok(positionOutput, 'position output should render');

  await act(async () => {
    header.dispatchEvent(new dom.window.MouseEvent('mousedown', {
      bubbles: true,
      cancelable: true,
      clientX: 50,
      clientY: 60,
    }));
  });

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousemove', {
      bubbles: true,
      cancelable: true,
      clientX: -200,
      clientY: 120,
      buttons: 1,
    }));
  });

  assert.ok(parseFloat(jointPanel.style.left) < 0);
  assert.equal(positionOutput.textContent, 'null');

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mouseup', {
      bubbles: true,
      cancelable: true,
      clientX: -200,
      clientY: 120,
    }));
  });

  const [committedX] = String(positionOutput.textContent ?? '').split(',');
  assert.ok(Number.parseFloat(committedX) < 0);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('joint panel dragging stays clear of the expanded left workspace sidebar', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderHarness(root, { '--workspace-overlay-left-inset': '264px' });

  const header = container.querySelector('#joint-header');
  const jointPanel = header?.parentElement as HTMLDivElement | null;
  const positionOutput = container.querySelector('#joint-pos');
  assert.ok(header, 'joint drag header should render');
  assert.ok(jointPanel, 'joint panel should render');
  assert.ok(positionOutput, 'position output should render');

  await act(async () => {
    header.dispatchEvent(new dom.window.MouseEvent('mousedown', {
      bubbles: true,
      cancelable: true,
      clientX: 50,
      clientY: 60,
    }));
  });

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousemove', {
      bubbles: true,
      cancelable: true,
      clientX: -200,
      clientY: 120,
      buttons: 1,
    }));
  });

  assert.equal(jointPanel.style.left, '266px');
  assert.equal(positionOutput.textContent, 'null');

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mouseup', {
      bubbles: true,
      cancelable: true,
      clientX: -200,
      clientY: 120,
    }));
  });

  assert.equal(positionOutput.textContent, '266,90');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('committed panel positions move right when the left workspace sidebar expands', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderHarness(root);

  const header = container.querySelector('#joint-header');
  const jointPanel = header?.parentElement as HTMLDivElement | null;
  const positionOutput = container.querySelector('#joint-pos');
  assert.ok(header, 'joint drag header should render');
  assert.ok(jointPanel, 'joint panel should render');
  assert.ok(positionOutput, 'position output should render');

  await act(async () => {
    header.dispatchEvent(new dom.window.MouseEvent('mousedown', {
      bubbles: true,
      cancelable: true,
      clientX: 50,
      clientY: 60,
    }));
  });

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mousemove', {
      bubbles: true,
      cancelable: true,
      clientX: 10,
      clientY: 60,
      buttons: 1,
    }));
  });

  await act(async () => {
    dom.window.document.dispatchEvent(new dom.window.MouseEvent('mouseup', {
      bubbles: true,
      cancelable: true,
      clientX: 10,
      clientY: 60,
    }));
  });

  assert.equal(positionOutput.textContent, '-20,30');

  await renderHarness(root, { '--workspace-overlay-left-inset': '264px' });

  assert.equal(positionOutput.textContent, '266,30');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

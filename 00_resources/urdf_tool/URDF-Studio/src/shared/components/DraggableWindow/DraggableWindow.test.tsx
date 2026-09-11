import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act, createRef } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { DraggableWindow } from './DraggableWindow';
import { APP_HEADER_HEIGHT_PX } from '@/shared/hooks/useDraggableWindow';
import { OverlayHoverBlockProvider } from '@/shared/hooks/useOverlayHoverBlock';
import { CLOSE_BUTTON_DANGER_INTERACTION_CLASS } from '@/shared/components/ui/closeButtonStyles';

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
  (globalThis as { PointerEvent?: typeof PointerEvent }).PointerEvent =
    dom.window.PointerEvent ?? dom.window.MouseEvent;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

test('DraggableWindow default close button uses the shared danger hover treatment', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const windowRef = createRef<HTMLDivElement>();

  try {
    await act(async () => {
      root.render(
        React.createElement(DraggableWindow, {
          window: {
            isMaximized: false,
            isMinimized: false,
            isDragging: false,
            isResizing: false,
            containerRef: windowRef,
            handleDragStart: () => {},
            handleResizeStart: () => {},
            toggleMaximize: () => {},
            toggleMinimize: () => {},
            windowStyle: {},
          },
          onClose: () => {},
          title: 'Export',
          closeTitle: 'Close',
          children: React.createElement('div', null, 'content'),
        }),
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

test('DraggableWindow activates the shared hover block while hovered and releases it on unmount', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const windowRef = createRef<HTMLDivElement>();
  const hoverBlockEvents: string[] = [];

  try {
    await act(async () => {
      root.render(
        React.createElement(
          OverlayHoverBlockProvider,
          {
            value: {
              beginHoverBlock: () => hoverBlockEvents.push('begin'),
              endHoverBlock: () => hoverBlockEvents.push('end'),
              clearHover: () => hoverBlockEvents.push('clear'),
            },
            children: React.createElement(DraggableWindow, {
              window: {
                isMaximized: false,
                isMinimized: false,
                isDragging: false,
                isResizing: false,
                containerRef: windowRef,
                handleDragStart: () => {},
                handleResizeStart: () => {},
                toggleMaximize: () => {},
                toggleMinimize: () => {},
                windowStyle: {},
              },
              onClose: () => {},
              title: 'Export',
              children: React.createElement('div', null, 'content'),
            }),
          },
        ),
      );
    });

    const windowRoot = container.firstElementChild as HTMLDivElement | null;
    assert.ok(windowRoot, 'draggable window should render');

    await act(async () => {
      windowRoot.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    });

    assert.deepEqual(hoverBlockEvents, ['begin', 'clear']);

    await act(async () => {
      root.unmount();
    });

    assert.deepEqual(hoverBlockEvents, ['begin', 'clear', 'end']);
  } finally {
    dom.window.close();
  }
});

test('DraggableWindow renders thin visual resize affordances inside wider hit targets', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const windowRef = createRef<HTMLDivElement>();

  try {
    await act(async () => {
      root.render(
        React.createElement(DraggableWindow, {
          window: {
            isMaximized: false,
            isMinimized: false,
            isDragging: false,
            isResizing: false,
            containerRef: windowRef,
            handleDragStart: () => {},
            handleResizeStart: () => {},
            toggleMaximize: () => {},
            toggleMinimize: () => {},
            windowStyle: {},
          },
          onClose: () => {},
          title: 'Export',
          children: React.createElement('div', null, 'content'),
        }),
      );
    });

    const resizeHandles = container.querySelectorAll<HTMLButtonElement>(
      'button[aria-label="Resize"]',
    );
    assert.equal(resizeHandles.length, 4);

    const rightHandleClassName = resizeHandles[1]?.className ?? '';
    const bottomHandleClassName = resizeHandles[2]?.className ?? '';
    const cornerHandleClassName = resizeHandles[3]?.className ?? '';
    const rightHandleClasses = rightHandleClassName.split(/\s+/);
    const bottomHandleClasses = bottomHandleClassName.split(/\s+/);

    assert.match(rightHandleClassName, /\bw-2\b/);
    assert.equal(rightHandleClassName.includes('resize-edge-right'), true);
    assert.equal(rightHandleClassName.includes('resize-edge-visual-right'), true);
    assert.equal(rightHandleClasses.includes('right-0'), false);
    assert.match(rightHandleClassName, /\bafter:w-px\b/);
    assert.match(rightHandleClassName, /\bhover:after:bg-system-blue/);
    assert.doesNotMatch(rightHandleClassName, /\bhover:bg-system-blue/);

    assert.match(bottomHandleClassName, /\bh-2\b/);
    assert.equal(bottomHandleClassName.includes('resize-edge-bottom'), true);
    assert.equal(bottomHandleClassName.includes('resize-edge-visual-bottom'), true);
    assert.equal(bottomHandleClasses.includes('bottom-0'), false);
    assert.match(bottomHandleClassName, /\bafter:h-px\b/);
    assert.match(bottomHandleClassName, /\bhover:after:bg-system-blue/);
    assert.doesNotMatch(bottomHandleClassName, /\bhover:bg-system-blue/);

    assert.match(cornerHandleClassName, /\bgroup\b/);
    assert.doesNotMatch(cornerHandleClassName, /\bhover:bg-system-blue/);
    assert.ok(
      resizeHandles[3]?.querySelector('.border-b.border-r'),
      'corner handle should render a thin corner mark instead of a hover block',
    );

    await act(async () => {
      root.unmount();
    });
  } finally {
    dom.window.close();
  }
});

test('DraggableWindow applies dynamic z-index and activates on pointer or keyboard focus', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const windowRef = createRef<HTMLDivElement>();
  let activateCount = 0;

  try {
    await act(async () => {
      root.render(
        React.createElement(DraggableWindow, {
          window: {
            isMaximized: false,
            isMinimized: false,
            isDragging: false,
            isResizing: false,
            containerRef: windowRef,
            handleDragStart: () => {},
            handleResizeStart: () => {},
            toggleMaximize: () => {},
            toggleMinimize: () => {},
            windowStyle: {},
          },
          zIndex: 237,
          onActivate: () => {
            activateCount += 1;
          },
          onClose: () => {},
          title: 'Layered',
          children: React.createElement('button', { type: 'button' }, 'Focusable'),
        }),
      );
    });

    const windowRoot = container.firstElementChild as HTMLDivElement | null;
    assert.ok(windowRoot, 'draggable window should render');
    assert.equal(windowRoot.style.zIndex, '237');

    await act(async () => {
      windowRoot.dispatchEvent(new dom.window.MouseEvent('pointerdown', { bubbles: true }));
    });
    assert.equal(activateCount, 1);

    const button = container.querySelector('button[type="button"]');
    assert.ok(button, 'focusable child should render');
    await act(async () => {
      button.dispatchEvent(new dom.window.Event('focusin', { bubbles: true }));
    });
    assert.equal(activateCount, 2);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('DraggableWindow leaves the app header exposed while maximized instead of covering it', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const windowRef = createRef<HTMLDivElement>();

  try {
    await act(async () => {
      root.render(
        React.createElement(DraggableWindow, {
          window: {
            isMaximized: true,
            isMinimized: false,
            isDragging: false,
            isResizing: false,
            containerRef: windowRef,
            handleDragStart: () => {},
            handleResizeStart: () => {},
            toggleMaximize: () => {},
            toggleMinimize: () => {},
            windowStyle: {
              position: 'fixed',
              top: APP_HEADER_HEIGHT_PX,
              left: 0,
              right: 0,
              bottom: 0,
              width: '100%',
              height: `calc(100% - ${APP_HEADER_HEIGHT_PX}px)`,
              transform: 'none',
            },
          },
          zIndex: 235,
          onActivate: () => {},
          onClose: () => {},
          title: 'Maximized',
          children: null,
        }),
      );
    });

    const windowRoot = container.firstElementChild as HTMLDivElement | null;
    assert.ok(windowRoot, 'draggable window should render');
    assert.equal(
      windowRoot.style.top,
      `${APP_HEADER_HEIGHT_PX}px`,
      'maximized window should start below the fixed app header',
    );
    assert.equal(
      windowRoot.style.height,
      `calc(100% - ${APP_HEADER_HEIGHT_PX}px)`,
      'maximized window should fill the viewport below the header',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

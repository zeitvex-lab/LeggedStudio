import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { ScanSearch } from 'lucide-react';

import { translations } from '@/shared/i18n';
import { ToolboxMenu } from './ToolboxMenu';
import type { ToolboxItem } from './types';

type TestRoot = {
  dom: JSDOM;
  container: HTMLDivElement;
  root: Root;
};

type MockRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type ResizeObserverMockInstance = {
  callback: ResizeObserverCallback;
  observedTargets: Element[];
  disconnectCount: number;
};

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'localStorage', {
    value: dom.window.localStorage,
    configurable: true,
  });

  const matchMediaStub = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });

  (globalThis as { matchMedia?: typeof window.matchMedia }).matchMedia = matchMediaStub;
  dom.window.matchMedia = matchMediaStub;

  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
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
  Object.defineProperty(globalThis, 'ResizeObserver', {
    value: undefined,
    configurable: true,
  });
  Object.defineProperty(dom.window, 'ResizeObserver', {
    value: undefined,
    configurable: true,
  });
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

function createComponentRoot(): TestRoot {
  const dom = installDom();
  const container = dom.window.document.createElement('div');
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  return { dom, container, root };
}

function makeTestItems(overrides?: {
  onAiInspectionClick?: () => void;
  onRobogoClick?: () => void;
}): ToolboxItem[] {
  return [
    {
      key: 'ai-inspection',
      title: translations.en.aiInspection,
      description: translations.en.aiInspectionDesc,
      icon: <ScanSearch className="h-[18px] w-[18px]" />,
      onClick: overrides?.onAiInspectionClick ?? (() => {}),
      tone: 'primary',
    },
    {
      key: 'robogo',
      title: translations.en.robogo,
      description: translations.en.robogoDesc,
      icon: <img src="/logos/d-robotics-logo.jpg" alt="" className="h-5 w-5" />,
      onClick: overrides?.onRobogoClick ?? (() => {}),
      external: true,
      tone: 'logo',
    },
  ];
}

function makeDomRect(dom: JSDOM, rect: MockRect): DOMRect {
  const right = rect.left + rect.width;
  const bottom = rect.top + rect.height;

  return {
    x: rect.left,
    y: rect.top,
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
    right,
    bottom,
    toJSON: () => ({ ...rect, right, bottom }),
  } as DOMRect;
}

function setViewportWidth(dom: JSDOM, width: number) {
  Object.defineProperty(dom.window, 'innerWidth', {
    value: width,
    configurable: true,
  });
  Object.defineProperty(dom.window.document.documentElement, 'clientWidth', {
    value: width,
    configurable: true,
  });
}

function installToolboxLayoutMock(
  dom: JSDOM,
  layout: {
    panel: MockRect;
    trigger: MockRect;
  },
) {
  Object.defineProperty(dom.window.HTMLElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    value(this: HTMLElement) {
      if (this.dataset.testid === 'toolbox-trigger') {
        return makeDomRect(dom, layout.trigger);
      }

      if (typeof this.className === 'string' && this.className.includes('w-[23rem]')) {
        return makeDomRect(dom, layout.panel);
      }

      return makeDomRect(dom, { left: 0, top: 0, width: 0, height: 0 });
    },
  });
}

function installResizeObserverMock(dom: JSDOM) {
  const instances: ResizeObserverMockInstance[] = [];

  class TestResizeObserver {
    readonly callback: ResizeObserverCallback;
    readonly observedTargets: Element[] = [];
    disconnectCount = 0;

    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
      instances.push(this);
    }

    observe(target: Element) {
      this.observedTargets.push(target);
    }

    unobserve(target: Element) {
      const index = this.observedTargets.indexOf(target);

      if (index >= 0) {
        this.observedTargets.splice(index, 1);
      }
    }

    disconnect() {
      this.disconnectCount += 1;
    }
  }

  Object.defineProperty(globalThis, 'ResizeObserver', {
    value: TestResizeObserver,
    configurable: true,
  });
  Object.defineProperty(dom.window, 'ResizeObserver', {
    value: TestResizeObserver,
    configurable: true,
  });

  const notifyTarget = (target: Element) => {
    for (const instance of instances) {
      if (!instance.observedTargets.includes(target)) {
        continue;
      }

      instance.callback([], instance as unknown as ResizeObserver);
    }
  };

  return { instances, notifyTarget };
}

function getToolboxPanel(container: HTMLElement): HTMLDivElement {
  const panel = Array.from(container.querySelectorAll<HTMLDivElement>('div')).find((element) =>
    element.className.includes('w-[23rem]'),
  );

  assert.ok(panel, 'toolbox panel should render');
  return panel;
}

async function renderPositionedToolboxMenu(root: Root) {
  await act(async () => {
    root.render(
      <div>
        <button type="button" data-testid="toolbox-trigger">
          Toolbox
        </button>
        <ToolboxMenu t={translations.en} onClose={() => {}} items={makeTestItems()} />
      </div>,
    );
  });
}

test('Toolbox menu triggers a supplied primary action and closes', async () => {
  const { dom, container, root } = createComponentRoot();
  let closed = false;
  let opened = false;

  const items = makeTestItems({
    onAiInspectionClick: () => {
      opened = true;
    },
  });

  await act(async () => {
    root.render(
      <ToolboxMenu
        t={translations.en}
        onClose={() => {
          closed = true;
        }}
        items={items}
      />,
    );
  });

  const actionButton = container.querySelector<HTMLButtonElement>(
    `button[aria-label="${translations.en.aiInspection}"]`,
  );
  assert.ok(actionButton, 'supplied toolbox entry should render');

  await act(async () => {
    actionButton!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  });

  assert.equal(opened, true);
  assert.equal(closed, true);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu clamps the dropdown inside a narrow left viewport', async () => {
  const { dom, container, root } = createComponentRoot();
  installResizeObserverMock(dom);
  setViewportWidth(dom, 380);
  installToolboxLayoutMock(dom, {
    trigger: { left: 125, top: 9, width: 34, height: 22 },
    panel: { left: 0, top: 35, width: 364, height: 269 },
  });

  await renderPositionedToolboxMenu(root);

  const panel = getToolboxPanel(container);
  assert.equal(panel.style.position, 'fixed');
  assert.equal(panel.style.left, '8px');
  assert.equal(panel.style.top, '35px');
  assert.doesNotMatch(panel.className, /\babsolute\b/);
  assert.doesNotMatch(panel.className, /\btranslate-x-1\/2\b/);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu clamps the dropdown inside a right viewport edge', async () => {
  const { dom, container, root } = createComponentRoot();
  installResizeObserverMock(dom);
  setViewportWidth(dom, 760);
  installToolboxLayoutMock(dom, {
    trigger: { left: 700, top: 9, width: 52, height: 22 },
    panel: { left: 0, top: 35, width: 368, height: 269 },
  });

  await renderPositionedToolboxMenu(root);

  const panel = getToolboxPanel(container);
  assert.equal(panel.style.position, 'fixed');
  assert.equal(panel.style.left, '384px');
  assert.equal(panel.style.top, '35px');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu observes trigger layout changes and recenters after responsive resize', async () => {
  const { dom, container, root } = createComponentRoot();
  const resizeObserver = installResizeObserverMock(dom);
  const layout = {
    trigger: { left: 125, top: 9, width: 34, height: 22 },
    panel: { left: 0, top: 35, width: 364, height: 269 },
  };
  setViewportWidth(dom, 380);
  installToolboxLayoutMock(dom, layout);

  await renderPositionedToolboxMenu(root);

  const panel = getToolboxPanel(container);
  const trigger = container.querySelector<HTMLButtonElement>('[data-testid="toolbox-trigger"]');
  assert.ok(trigger, 'toolbox trigger should render');
  assert.equal(panel.style.left, '8px');
  assert.ok(
    resizeObserver.instances.some((instance) => instance.observedTargets.includes(trigger)),
    'trigger should be observed so responsive header relayouts recompute menu position',
  );

  setViewportWidth(dom, 1280);
  layout.trigger = { left: 214, top: 8, width: 101, height: 23 };
  layout.panel = { left: 8, top: 35, width: 368, height: 269 };

  await act(async () => {
    resizeObserver.notifyTarget(trigger);
    await new Promise<void>((resolve) => {
      dom.window.requestAnimationFrame(() => resolve());
    });
  });

  assert.equal(panel.style.left, '81px');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu keeps default CSS positioning when layout measurements are unavailable', async () => {
  const { dom, container, root } = createComponentRoot();
  setViewportWidth(dom, 380);
  installToolboxLayoutMock(dom, {
    trigger: { left: 0, top: 0, width: 0, height: 0 },
    panel: { left: 0, top: 0, width: 0, height: 0 },
  });

  await renderPositionedToolboxMenu(root);

  const panel = getToolboxPanel(container);
  assert.equal(panel.style.position, '');
  assert.match(panel.className, /\babsolute\b/);
  assert.match(panel.className, /\btop-full\b/);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu no longer renders the measure entry', async () => {
  const { dom, container, root } = createComponentRoot();
  const items = makeTestItems();

  await act(async () => {
    root.render(<ToolboxMenu t={translations.en} onClose={() => {}} items={items} />);
  });

  const measureButton = container.querySelector<HTMLButtonElement>(
    `button[aria-label="${translations.en.measureMode}"]`,
  );
  assert.equal(measureButton, null);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('Toolbox menu exposes the RoboGo external entry and closes on click', async () => {
  const { dom, container, root } = createComponentRoot();
  let closed = false;
  let robogoClicked = false;

  const items = makeTestItems({
    onRobogoClick: () => {
      robogoClicked = true;
    },
  });

  await act(async () => {
    root.render(
      <ToolboxMenu
        t={translations.en}
        onClose={() => {
          closed = true;
        }}
        items={items}
      />,
    );
  });

  const robogoButton = container.querySelector<HTMLButtonElement>(
    `button[aria-label="${translations.en.robogo}"]`,
  );
  assert.ok(robogoButton, 'RoboGo toolbox entry should render');

  await act(async () => {
    robogoButton!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  });

  assert.equal(closed, true);
  assert.equal(robogoClicked, true);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

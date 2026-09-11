import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { translations } from '@/shared/i18n';
import { IkToolPanel } from './IkToolPanel';

type TestRoot = {
  dom: JSDOM;
  container: HTMLDivElement;
  root: Root;
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

  const matchMediaStub = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;

  (globalThis as { matchMedia?: typeof window.matchMedia }).matchMedia = matchMediaStub;
  dom.window.matchMedia = matchMediaStub;

  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
  (globalThis as { HTMLInputElement?: typeof HTMLInputElement }).HTMLInputElement =
    dom.window.HTMLInputElement;
  (globalThis as { HTMLSelectElement?: typeof HTMLSelectElement }).HTMLSelectElement =
    dom.window.HTMLSelectElement;
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

function createComponentRoot(): TestRoot {
  const dom = installDom();
  const container = dom.window.document.createElement('div');
  dom.window.document.body.appendChild(container);
  const root = createRoot(container);
  return { dom, container, root };
}

async function renderIkPanel(
  root: Root,
  overrides: Partial<React.ComponentProps<typeof IkToolPanel>> = {},
) {
  await act(async () => {
    root.render(
      <IkToolPanel
        show
        t={translations.en}
        linkOptions={[{ value: 'tool_link', label: 'tool_link' }]}
        selectedLinkId={null}
        currentLinkLabel={null}
        selectedLinkLabel={null}
        selectionStatus="idle"
        onSelectLink={() => {}}
        onClose={() => {}}
        {...overrides}
      />,
    );
  });
}

test('IkToolPanel renders the selected-link status, help text, and Link selector without a toggle', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderIkPanel(root);

  const toggle = container.querySelector('button[role="switch"]');
  assert.equal(toggle, null, 'IK drag toggle should not render');
  assert.equal(container.textContent?.includes(translations.en.ikToolboxDesc), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolSelectLink), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolSelectedLink), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolNoSelection), true);
  assert.ok(container.querySelector('select'), 'link selector should render');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('IkToolPanel emits selected Link changes from the selector', async () => {
  const { dom, container, root } = createComponentRoot();
  let selectedLinkId: string | null = null;

  await renderIkPanel(root, {
    onSelectLink: (linkId) => {
      selectedLinkId = linkId;
    },
  });

  const linkSelect = container.querySelector('select') as HTMLSelectElement | null;
  assert.ok(linkSelect, 'link selector should render');

  await act(async () => {
    linkSelect.value = 'tool_link';
    linkSelect.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });

  assert.equal(selectedLinkId, 'tool_link');

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('IkToolPanel disables the Link selector when no IK-draggable links exist', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderIkPanel(root, {
    linkOptions: [],
  });

  const linkSelect = container.querySelector('select') as HTMLSelectElement | null;
  assert.ok(linkSelect, 'link selector should render');
  assert.equal(linkSelect.disabled, true);
  assert.equal(container.textContent?.includes(translations.en.ikToolSelectPlaceholder), true);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('IkToolPanel shows the current IK link label when one is selected', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderIkPanel(root, {
    selectedLinkId: 'tool_link',
    selectedLinkLabel: 'tool_tip_link',
    selectionStatus: 'selected',
  });

  assert.equal(container.textContent?.includes('tool_tip_link'), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolNoSelection), false);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('IkToolPanel shows the clicked link and a clear reason when the link cannot be dragged with IK', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderIkPanel(root, {
    currentLinkLabel: 'base_link',
    selectionStatus: 'root_not_draggable',
  });

  assert.equal(container.textContent?.includes('base_link'), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolRootLinkNotDraggable), true);
  assert.equal(container.textContent?.includes(translations.en.ikToolNoSelection), false);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

test('IkToolPanel can be repositioned by dragging its header', async () => {
  const { dom, container, root } = createComponentRoot();

  await renderIkPanel(root);

  const panelRoot = container.querySelector('.ik-tool-panel') as HTMLDivElement | null;
  assert.ok(panelRoot, 'IK panel root should render');

  panelRoot.getBoundingClientRect = () =>
    ({
      left: 0,
      top: 0,
      width: 224,
      height: 180,
      right: 224,
      bottom: 180,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;

  const dragHeader = panelRoot.firstElementChild?.firstElementChild as HTMLDivElement | null;
  assert.ok(dragHeader, 'IK panel drag header should render');

  await act(async () => {
    dragHeader.dispatchEvent(
      new dom.window.MouseEvent('mousedown', {
        bubbles: true,
        cancelable: true,
        clientX: 80,
        clientY: 90,
      }),
    );
  });

  await act(async () => {
    dom.window.document.dispatchEvent(
      new dom.window.MouseEvent('mousemove', {
        bubbles: true,
        cancelable: true,
        clientX: 260,
        clientY: 180,
        buttons: 1,
      }),
    );
  });

  assert.equal(panelRoot.style.left, '180px');
  assert.equal(panelRoot.style.top, '90px');

  await act(async () => {
    dom.window.document.dispatchEvent(
      new dom.window.MouseEvent('mouseup', {
        bubbles: true,
        cancelable: true,
        clientX: 260,
        clientY: 180,
      }),
    );
  });

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

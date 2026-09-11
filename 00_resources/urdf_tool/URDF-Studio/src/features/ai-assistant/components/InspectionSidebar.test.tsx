import assert from 'node:assert/strict';
import test from 'node:test';

import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { JSDOM } from 'jsdom';

import { translations } from '@/shared/i18n';
import { INSPECTION_PROFILE_DEFINITIONS } from '../config/inspectionProfiles';
import { InspectionSidebar } from './InspectionSidebar';

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

function createSelectedItems() {
  return Object.fromEntries(
    INSPECTION_PROFILE_DEFINITIONS.map((profile) => [
      profile.id,
      new Set(profile.items.map((item) => item.id)),
    ]),
  );
}

test('setup inspection sidebar groups selectable profiles by profile layer', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const selectedProfiles = createSelectedItems();

  try {
    await act(async () => {
      root.render(
        <InspectionSidebar
          lang="zh"
          t={translations.zh}
          isGeneratingAI={false}
          readOnly={false}
          focusedProfileId={INSPECTION_PROFILE_DEFINITIONS[0]?.id ?? ''}
          expandedProfiles={new Set(INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id))}
          selectedProfiles={selectedProfiles}
          recommendedProfiles={selectedProfiles}
          setExpandedProfiles={() => {}}
          setSelectedProfiles={() => {}}
          onFocusProfile={() => {}}
        />,
      );
    });

    const layerSections = Array.from(
      container.querySelectorAll<HTMLElement>('[data-inspection-sidebar-layer]'),
    );

    assert.equal(layerSections.length, 5, 'expected one sidebar section per profile layer');
    ['基础通用层', '机器人形态层', '源格式层', '目标平台层', '工作流层'].forEach((layerName) => {
      assert.equal(
        layerSections.some((section) => section.textContent?.includes(layerName)),
        true,
        `expected ${layerName} layer section to render`,
      );
    });
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('setup inspection sidebar lets a profile layer collapse and expand', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const selectedProfiles = createSelectedItems();
  const baseProfile = INSPECTION_PROFILE_DEFINITIONS.find((profile) => profile.layer === 'base');
  assert.ok(baseProfile, 'expected a base-layer profile');
  const focusedProfileId = baseProfile.id;

  function SidebarHarness() {
    const [expandedProfiles, setExpandedProfiles] = useState(
      new Set(INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id)),
    );
    const [localSelectedProfiles, setSelectedProfiles] = useState(selectedProfiles);

    return (
      <InspectionSidebar
        lang="zh"
        t={translations.zh}
        isGeneratingAI={false}
        readOnly={false}
        focusedProfileId={focusedProfileId}
        expandedProfiles={expandedProfiles}
        selectedProfiles={localSelectedProfiles}
        recommendedProfiles={selectedProfiles}
        setExpandedProfiles={setExpandedProfiles}
        setSelectedProfiles={setSelectedProfiles}
        onFocusProfile={() => {}}
      />
    );
  }

  try {
    await act(async () => {
      root.render(<SidebarHarness />);
    });

    const baseLayerToggle = container.querySelector<HTMLButtonElement>(
      '[data-inspection-sidebar-layer-toggle="base"]',
    );
    assert.ok(baseLayerToggle, 'expected the base layer toggle to render');
    assert.equal(
      baseLayerToggle.getAttribute('aria-expanded'),
      'true',
      'expected the base layer to start expanded',
    );
    assert.equal(
      container.textContent?.includes(baseProfile.nameZh),
      true,
      'expected expanded base layer to show its profiles',
    );

    await act(async () => {
      baseLayerToggle.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.equal(
      baseLayerToggle.getAttribute('aria-expanded'),
      'false',
      'expected clicking the base layer header to collapse it',
    );
    assert.equal(
      container.textContent?.includes(baseProfile.nameZh),
      false,
      'expected collapsed base layer to hide its profiles',
    );

    await act(async () => {
      baseLayerToggle.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.equal(
      baseLayerToggle.getAttribute('aria-expanded'),
      'true',
      'expected clicking the base layer header again to expand it',
    );
    assert.equal(
      container.textContent?.includes(baseProfile.nameZh),
      true,
      'expected expanded base layer to show its profiles again',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('setup inspection sidebar item labels navigate without toggling selection', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const selectedProfiles = createSelectedItems();
  const firstProfile = INSPECTION_PROFILE_DEFINITIONS[0];
  const firstItem = firstProfile?.items[0];
  assert.ok(firstProfile, 'expected an inspection profile');
  assert.ok(firstItem, 'expected an inspection item');
  let navigatedTarget: string | null = null;

  function SidebarHarness() {
    const [expandedProfiles, setExpandedProfiles] = useState(new Set([firstProfile.id]));
    const [localSelectedProfiles, setSelectedProfiles] = useState(selectedProfiles);

    return (
      <InspectionSidebar
        lang="zh"
        t={translations.zh}
        isGeneratingAI={false}
        readOnly={false}
        focusedProfileId={firstProfile.id}
        expandedProfiles={expandedProfiles}
        selectedProfiles={localSelectedProfiles}
        recommendedProfiles={selectedProfiles}
        setExpandedProfiles={setExpandedProfiles}
        setSelectedProfiles={setSelectedProfiles}
        onFocusProfile={() => {}}
        onNavigateToSetupItem={(profileId, itemId) => {
          navigatedTarget = `${profileId}:${itemId}`;
        }}
      />
    );
  }

  try {
    await act(async () => {
      root.render(<SidebarHarness />);
    });

    const itemLabelButton = container.querySelector<HTMLButtonElement>(
      `[data-inspection-sidebar-item-link="${firstProfile.id}:${firstItem.id}"]`,
    );
    assert.ok(itemLabelButton, 'expected an item navigation button to render');

    await act(async () => {
      itemLabelButton.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.equal(
      navigatedTarget,
      `${firstProfile.id}:${firstItem.id}`,
      'expected clicking the item label to request navigation',
    );
    assert.equal(
      container.textContent?.includes(translations.zh.inspectionSkipped),
      false,
      'expected item navigation to avoid toggling the item selection',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('professional setup sidebar shows per-profile recommendation delta badges', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  const selectedProfiles = {
    'base.robot_model': new Set(['model_identity']),
    'format.urdf': new Set(['urdf_robot_root']),
  };
  const recommendedProfiles = {
    'base.robot_model': new Set(['model_identity', 'tree_connectivity']),
  };

  try {
    await act(async () => {
      root.render(
        <InspectionSidebar
          lang="en"
          t={translations.en}
          isGeneratingAI={false}
          readOnly={false}
          focusedProfileId="base.robot_model"
          expandedProfiles={new Set(['base.robot_model', 'format.urdf'])}
          selectedProfiles={selectedProfiles}
          recommendedProfiles={recommendedProfiles}
          setExpandedProfiles={() => {}}
          setSelectedProfiles={() => {}}
          onFocusProfile={() => {}}
        />,
      );
    });

    const baseDelta = container.querySelector<HTMLElement>(
      '[data-inspection-profile-delta="base.robot_model"]',
    );
    const formatDelta = container.querySelector<HTMLElement>(
      '[data-inspection-profile-delta="format.urdf"]',
    );

    assert.ok(baseDelta, 'expected a removed-item delta badge on the partially excluded profile');
    assert.equal(baseDelta.textContent?.trim(), '-1');
    assert.ok(formatDelta, 'expected an added-item delta badge on the user-added profile');
    assert.equal(formatDelta.textContent?.trim(), '+1');
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('running inspection sidebar keeps scroll container interactive without rendering the checking badge', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(
        <InspectionSidebar
          lang="zh"
          t={translations.zh}
          isGeneratingAI
          readOnly
          focusedProfileId={INSPECTION_PROFILE_DEFINITIONS[0]?.id ?? ''}
          expandedProfiles={new Set(INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id))}
          selectedProfiles={createSelectedItems()}
          setExpandedProfiles={() => {}}
          setSelectedProfiles={() => {}}
          onFocusProfile={() => {}}
        />,
      );
    });

    const scrollContainer = container.querySelector('.custom-scrollbar');
    assert.ok(scrollContainer, 'expected sidebar scroll container to render');
    assert.equal(
      scrollContainer.classList.contains('pointer-events-none'),
      false,
      'running inspection should keep the sidebar scroll area available for wheel/trackpad scrolling',
    );

    const toggleButtons = Array.from(container.querySelectorAll('button'));
    assert.ok(toggleButtons.length > 0, 'expected profile expand buttons to render');
    assert.equal(
      toggleButtons.every((button) => (button as HTMLButtonElement).disabled),
      true,
      'running inspection should lock sidebar controls without disabling scrolling on the container',
    );

    const checkingBadge = Array.from(container.querySelectorAll('span')).find(
      (element) => element.textContent?.trim() === translations.zh.checking,
    );
    assert.equal(
      checkingBadge,
      undefined,
      'running inspection sidebar should not render the checking badge in the header',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { translations } from '@/shared/i18n';
import { InspectionProgress } from './InspectionProgress';

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

function mockCarouselSlideHeights(dom: JSDOM) {
  Object.defineProperty(dom.window.HTMLElement.prototype, 'scrollHeight', {
    configurable: true,
    get() {
      if (this.getAttribute('data-inspection-running-carousel-slide-content') === 'stage') {
        return 84;
      }

      if (this.getAttribute('data-inspection-running-carousel-slide-content') === 'profiles') {
        return 132;
      }

      return 0;
    },
  });
}

test('running inspection progress view renders a single cinematic console with truthful carousel content', async () => {
  const dom = installDom();
  mockCarouselSlideHeights(dom);
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(
        <InspectionProgress
          progress={{
            stage: 'requesting-model',
            selectedCount: 6,
          }}
          elapsedSeconds={12}
          runContext={{
            robotName: 'inspection-fixture',
            sourceValue: 'URDF',
            linkCount: 12,
            jointCount: 10,
            selectedCount: 6,
            selectedProfileCount: 2,
            estimatedDuration: {
              label: '10-20s',
              maxSeconds: 20,
            },
            profileSummary: [
              {
                id: 'kinematics',
                name: 'Kinematics',
                selectedCount: 3,
                totalCount: 5,
              },
              {
                id: 'physics',
                name: 'Physics',
                selectedCount: 2,
                totalCount: 5,
              },
              {
                id: 'simulation',
                name: 'Simulation',
                selectedCount: 4,
                totalCount: 5,
              },
              {
                id: 'maintenance',
                name: 'Maintenance',
                selectedCount: 1,
                totalCount: 5,
              },
              {
                id: 'urdf',
                name: 'URDF Source',
                selectedCount: 5,
                totalCount: 5,
              },
            ],
            evidenceSummary: null,
          }}
          t={translations.zh}
        />,
      );
    });

    assert.match(
      container.textContent ?? '',
      new RegExp(translations.zh.inspectionRequestingModel),
      'expected the active stage content to remain visible during a running inspection',
    );
    const runningShell = container.querySelector('[data-inspection-running-shell="true"]');
    assert.ok(runningShell, 'expected the simplified running shell to render');
    const runningConsole = container.querySelector(
      '[data-inspection-running-console="true"]',
    ) as HTMLElement | null;
    assert.ok(runningConsole, 'expected the running view to collapse into a single console panel');
    assert.ok(
      container.querySelector('[data-inspection-running-scan-core="true"]'),
      'expected the console to include a scanner-style live visual',
    );
    assert.ok(
      container.querySelector('[data-inspection-running-carousel="true"]'),
      'expected the console to rotate truthful context snippets in a carousel',
    );
    const carousel = container.querySelector(
      '[data-inspection-running-carousel="true"]',
    ) as HTMLElement | null;
    assert.ok(carousel, 'expected the running carousel to render');
    assert.equal(
      carousel.classList.contains('min-h-[140px]'),
      false,
      'expected the carousel not to use a fixed tall height for every slide',
    );
    assert.equal(
      carousel.style.height,
      '96px',
      'expected the carousel height to adapt to the active slide content with a small clipping buffer',
    );
    assert.equal(
      container.querySelector('[data-inspection-running-carousel-slide-active="true"]')
        ?.getAttribute('data-inspection-running-carousel-slide'),
      'stage',
      'expected the active carousel slide to be marked for measurement and visibility',
    );
    assert.equal(
      container
        .querySelector('[data-inspection-running-carousel-slide-content="stage"]')
        ?.parentElement?.getAttribute('data-inspection-running-carousel-slide-active'),
      'true',
      'expected carousel height measurement to use the active slide content instead of the stretched slide shell',
    );
    assert.equal(
      container.querySelectorAll('[data-inspection-running-carousel-slide]').length,
      2,
      'expected the carousel to include only stage and profile coverage slides',
    );
    assert.equal(
      container.querySelector('[data-inspection-running-carousel-slide="scope"]'),
      null,
      'expected the carousel not to include the inspection scope slide',
    );
    assert.equal(
      container.querySelector('[data-inspection-running-status-bar="true"]'),
      null,
      'expected the separate running status bar to be removed',
    );
    assert.equal(
      container.querySelector('[data-inspection-status-tray="true"]'),
      null,
      'expected the old stacked status tray to be removed from the running view',
    );
    assert.equal(
      runningConsole.textContent?.includes(translations.zh.aiInspection),
      false,
      'expected the running console not to repeat the AI inspection label above the title',
    );
    assert.equal(
      runningConsole.textContent?.includes(translations.zh.inspectionStageInProgress),
      false,
      'expected the running console not to show the redundant in-progress badge text',
    );
    assert.match(
      runningConsole.textContent ?? '',
      /6/,
      'expected the console to include the selected check count',
    );
    assert.match(
      runningConsole.textContent ?? '',
      /2/,
      'expected the console to include the selected profile count',
    );
    const elapsedBadge = container.querySelector('[data-inspection-elapsed-badge="true"]');
    assert.ok(elapsedBadge, 'expected elapsed time to render beside the active stage title');
    assert.ok(
      container.querySelector('[data-inspection-running-title-row="true"]')?.contains(elapsedBadge),
      'expected elapsed time to sit in the title row after the active stage name',
    );
    assert.equal(
      container.querySelector('[data-inspection-running-meta="true"]'),
      null,
      'expected the running view not to render a separate metadata row above the title',
    );
    assert.match(
      elapsedBadge.textContent ?? '',
      new RegExp(translations.zh.inspectionElapsedTime),
      'expected the elapsed badge to use the localized elapsed label',
    );
    assert.equal(
      elapsedBadge.textContent?.includes('12s') ?? false,
      true,
      'expected the elapsed badge to show the current elapsed duration',
    );
    assert.equal(
      container.querySelector('[data-inspection-estimated-badge="true"]'),
      null,
      'expected the running view not to show estimated duration because it is not live evidence',
    );
    assert.equal(
      container.textContent?.includes(translations.zh.inspectionEstimatedDuration),
      false,
      'expected the running view not to show any estimated duration copy',
    );
    assert.equal(
      container.textContent?.includes('10-20s'),
      false,
      'expected the running view not to show a static duration estimate',
    );
    const currentStageCard = container.querySelector(
      '[data-inspection-current-stage-card="true"]',
    ) as HTMLElement | null;
    assert.equal(
      currentStageCard,
      null,
      'expected the separate current stage card to be folded into the console',
    );
    assert.match(
      runningConsole.textContent ?? '',
      new RegExp(translations.zh.inspectionRequestingModelDescription),
      'expected the active stage description to remain visible',
    );
    assert.equal(
      container.querySelector('[data-inspection-stage-timeline="true"]'),
      null,
      'expected the running view not to show staged cards that do not advance with real progress',
    );
    assert.equal(
      container.querySelector('[data-inspection-running-progress-line="true"]'),
      null,
      'expected the running view not to show a pseudo progress bar',
    );
    const scopeSummary = container.querySelector(
      '[data-inspection-running-scope="true"]',
    ) as HTMLElement | null;
    assert.equal(
      scopeSummary,
      null,
      'expected the standalone scope card to be removed',
    );
    assert.equal(
      runningConsole.textContent?.includes(translations.zh.inspectionRunScope),
      false,
      'expected the running console not to show inspection scope copy',
    );
    assert.match(
      runningConsole.textContent ?? '',
      /Kinematics 3\/5/,
      'expected the carousel to include selected profile chips',
    );
    assert.match(runningConsole.textContent ?? '', /Physics 2\/5/);
    assert.match(runningConsole.textContent ?? '', /Simulation 4\/5/);
    assert.match(runningConsole.textContent ?? '', /Maintenance 1\/5/);
    assert.match(runningConsole.textContent ?? '', /URDF Source 5\/5/);
    const profileChips = container.querySelectorAll(
      '[data-inspection-running-profile-chip="true"]',
    );
    assert.equal(profileChips.length, 5, 'expected every selected profile to render as a chip');
    profileChips.forEach((chip) => {
      assert.equal(
        (chip as HTMLElement).classList.contains('whitespace-nowrap'),
        true,
        'profile chips should keep labels intact while wrapping as whole chips across rows',
      );
    });
    assert.equal(
      runningConsole.textContent?.includes('+1'),
      false,
      'expected profile coverage to show every selected profile instead of collapsing with a +N chip',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('running inspection status does not render delay hints derived from estimates', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(
        <InspectionProgress
          progress={{
            stage: 'processing-response',
            selectedCount: 6,
          }}
          elapsedSeconds={26}
          runContext={{
            robotName: 'inspection-fixture',
            sourceValue: 'URDF',
            linkCount: 12,
            jointCount: 10,
            selectedCount: 6,
            selectedProfileCount: 2,
            estimatedDuration: {
              label: '10-20s',
              maxSeconds: 20,
            },
            profileSummary: [
              {
                id: 'kinematics',
                name: 'Kinematics',
                selectedCount: 3,
                totalCount: 5,
              },
            ],
            evidenceSummary: null,
          }}
          t={translations.zh}
        />,
      );
    });

    const runningConsole = container.querySelector(
      '[data-inspection-running-console="true"]',
    ) as HTMLElement | null;
    assert.ok(runningConsole, 'expected the running console to render for long-running inspections');

    const elapsedBadge = container.querySelector(
      '[data-inspection-elapsed-badge="true"]',
    ) as HTMLElement | null;
    assert.ok(elapsedBadge, 'expected the elapsed badge to remain visible for delayed inspections');

    assert.equal(
      container.querySelector('[data-inspection-delayed-indicator="true"]'),
      null,
      'expected the running view not to infer delayed status from an estimated duration',
    );
    assert.equal(
      container.textContent?.includes(translations.zh.inspectionRunDelayed),
      false,
      'expected the running view not to show delayed copy derived from static estimates',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

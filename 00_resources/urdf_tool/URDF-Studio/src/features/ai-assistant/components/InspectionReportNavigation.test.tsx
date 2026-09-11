import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { translations } from '@/shared/i18n';
import { GeometryType, JointType, type InspectionReport, type RobotState } from '@/types';
import { INSPECTION_PROFILE_DEFINITIONS } from '../config/inspectionProfiles';
import type { SelectedInspectionProfiles } from '../utils/inspectionProfileSelection';
import { buildInspectionItemAnchorId, InspectionReportView } from './InspectionReport';
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
  Object.defineProperty(globalThis, 'localStorage', {
    value: dom.window.localStorage,
    configurable: true,
  });
  Object.defineProperty(globalThis, 'sessionStorage', {
    value: dom.window.sessionStorage,
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

const createRobotFixture = (): RobotState => ({
  name: 'inspection-fixture',
  rootLinkId: 'base_link',
  links: {
    base_link: {
      id: 'base_link',
      name: 'base_link',
      visual: {
        type: GeometryType.BOX,
        dimensions: { x: 0.4, y: 0.2, z: 0.1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        color: '#999999',
      },
      collision: {
        type: GeometryType.BOX,
        dimensions: { x: 0.4, y: 0.2, z: 0.1 },
        origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
        color: '#999999',
      },
      inertial: {
        mass: 2.5,
        inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
      },
    },
  },
  joints: {
    hip_joint: {
      id: 'hip_joint',
      name: 'hip_joint',
      type: JointType.REVOLUTE,
      parentLinkId: 'world',
      childLinkId: 'base_link',
      origin: { xyz: { x: 0, y: 0.1, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      axis: { x: 0, y: 1, z: 0 },
      limit: { lower: -1, upper: 1, effort: 20, velocity: 10 },
      dynamics: { damping: 0.1, friction: 0.1 },
      hardware: { armature: 0.03, motorType: 'servo', motorId: 'M1', motorDirection: 1 },
    },
  },
  inspectionContext: undefined,
  selection: { type: 'link', id: 'base_link' },
});

test('read-only inspection sidebar scrolls to the matching report item anchor', async () => {
  const dom = installDom();
  const scrollCalls: string[] = [];
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  Object.defineProperty(dom.window.HTMLElement.prototype, 'scrollIntoView', {
    value(this: HTMLElement) {
      scrollCalls.push(this.dataset.inspectionAnchorId ?? this.id);
    },
    configurable: true,
  });

  const [firstProfile, secondProfile, thirdProfile] = INSPECTION_PROFILE_DEFINITIONS;
  assert.ok(firstProfile, 'expected at least one inspection profile');
  assert.ok(secondProfile, 'expected at least two inspection profiles');
  assert.ok(thirdProfile, 'expected at least three inspection profiles');

  const firstItem = firstProfile.items[0];
  const secondItem = secondProfile.items[0];
  assert.ok(firstItem, 'expected the first profile to contain an inspection item');
  assert.ok(secondItem, 'expected the second profile to contain an inspection item');

  const selectedProfiles: SelectedInspectionProfiles = {
    [firstProfile.id]: new Set([firstItem.id]),
    [secondProfile.id]: new Set([secondItem.id]),
  };

  const report: InspectionReport = {
    summary: 'Navigation-ready report',
    issues: [
      {
        type: 'warning',
        title: `${firstItem.name} needs attention`,
        description: 'The first selected check reported a warning.',
        profileId: firstProfile.id,
        itemId: firstItem.id,
        score: 5,
      },
      {
        type: 'pass',
        title: `${secondItem.name} passed`,
        description: 'The second selected check passed cleanly.',
        profileId: secondProfile.id,
        itemId: secondItem.id,
        score: 10,
      },
    ],
    overallScore: 15,
    profileScores: {
      [firstProfile.id]: 5,
      [secondProfile.id]: 10,
    },
    maxScore: 20,
  };

  function NavigationHarness() {
    const [expandedProfiles, setExpandedProfiles] = useState<Set<string>>(
      new Set(INSPECTION_PROFILE_DEFINITIONS.map((profile) => profile.id)),
    );
    const [focusedProfileId, setFocusedProfileId] = useState(firstProfile.id);
    const scrollViewportRef = useRef<HTMLDivElement | null>(null);
    const t = translations.en;

    const ensureProfileExpanded = (profileId: string) => {
      setExpandedProfiles((prev) => {
        if (prev.has(profileId)) {
          return prev;
        }

        const next = new Set(prev);
        next.add(profileId);
        return next;
      });
    };

    const scrollToAnchor = (anchorId: string) => {
      const target = scrollViewportRef.current?.querySelector<HTMLElement>(
        `[data-inspection-anchor-id="${anchorId}"]`,
      );
      target?.scrollIntoView();
    };

    return (
      <div className="flex">
        <InspectionSidebar
          lang="en"
          t={t}
          isGeneratingAI={false}
          readOnly
          focusedProfileId={focusedProfileId}
          expandedProfiles={expandedProfiles}
          selectedProfiles={selectedProfiles}
          setExpandedProfiles={setExpandedProfiles}
          setSelectedProfiles={(value) => {
            void value;
          }}
          onFocusProfile={setFocusedProfileId}
          onNavigateToProfile={(profileId) => {
            setFocusedProfileId(profileId);
            ensureProfileExpanded(profileId);
          }}
          onNavigateToItem={(profileId, itemId) => {
            setFocusedProfileId(profileId);
            ensureProfileExpanded(profileId);
            scrollToAnchor(buildInspectionItemAnchorId(profileId, itemId));
          }}
        />

        <div ref={scrollViewportRef}>
          <InspectionReportView
            report={report}
            robot={createRobotFixture()}
            lang="en"
            t={t}
            expandedProfiles={expandedProfiles}
            retestingItem={null}
            isGeneratingAI={false}
            onToggleProfile={(profileId) => {
              setExpandedProfiles((prev) => {
                const next = new Set(prev);
                if (next.has(profileId)) {
                  next.delete(profileId);
                } else {
                  next.add(profileId);
                }
                return next;
              });
            }}
            onRetestItem={() => {}}
            onDownloadPDF={() => {}}
            onSelectItem={() => {}}
            onAskAboutIssue={() => {}}
          />
        </div>
      </div>
    );
  }

  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(<NavigationHarness />);
    });

    const thirdProfileName = thirdProfile.name;
    assert.equal(
      container.textContent?.includes(thirdProfileName),
      false,
      'unselected profiles should be hidden in the report navigation layout',
    );

    const targetAnchorId = buildInspectionItemAnchorId(firstProfile.id, firstItem.id);
    assert.ok(
      container.querySelector(`[data-inspection-anchor-id="${targetAnchorId}"]`),
      'expected the report item anchor to be rendered',
    );

    const itemButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes(firstItem.name),
    );
    assert.ok(itemButton, 'expected the selected sidebar item to render as a button');

    await act(async () => {
      itemButton!.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    assert.equal(
      scrollCalls.at(-1),
      targetAnchorId,
      'clicking a read-only sidebar item should scroll the matching report item into view',
    );
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

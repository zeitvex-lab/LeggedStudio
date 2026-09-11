import assert from 'node:assert/strict';
import test, { beforeEach } from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { createSingleComponentWorkspace } from '@/core/robot';
import { useSelectionStore, useUIStore } from '@/store';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  type AssemblyState,
  type RobotData,
  type WorkspaceSelection,
} from '@/types';

import {
  resolveParentJointAttentionSelection,
  useViewerOrchestration,
} from './useViewerOrchestration.ts';

function createRobot(name: string): RobotData {
  return {
    name,
    rootLinkId: 'base',
    links: {
      base: { ...structuredClone(DEFAULT_LINK), id: 'base', name: 'base' },
      tool: { ...structuredClone(DEFAULT_LINK), id: 'tool', name: 'tool' },
    },
    joints: {
      wrist: {
        ...structuredClone(DEFAULT_JOINT),
        id: 'wrist',
        name: 'wrist',
        parentLinkId: 'base',
        childLinkId: 'tool',
      },
    },
  };
}

function createWorkspace(): AssemblyState {
  const workspace = createSingleComponentWorkspace(createRobot('left'), {
    componentId: 'left',
  });
  workspace.components.right = {
    ...structuredClone(workspace.components.left!),
    id: 'right',
    name: 'right',
    robot: createRobot('right'),
  };
  return workspace;
}

function renderHook(
  workspace: AssemblyState,
  overrides: Partial<Parameters<typeof useViewerOrchestration>[0]> = {},
): ReturnType<typeof useViewerOrchestration> {
  const hookValue: { current: ReturnType<typeof useViewerOrchestration> | null } = {
    current: null,
  };
  const options: Parameters<typeof useViewerOrchestration>[0] = {
    workspace,
    setSelection: useSelectionStore.getState().setSelection,
    pulseSelection: useSelectionStore.getState().pulseSelection,
    setHoveredSelection: useSelectionStore.getState().setHoveredSelection,
    focusOn: useSelectionStore.getState().focusOn,
    transformPendingRef: { current: false },
    ...overrides,
  };
  function Probe() {
    hookValue.current = useViewerOrchestration(options);
    return null;
  }
  renderToStaticMarkup(React.createElement(Probe));
  assert.ok(hookValue.current);
  return hookValue.current;
}

beforeEach(() => {
  useSelectionStore.setState({
    selection: null,
    hoveredSelection: null,
    deferredHoveredSelection: null,
    attentionSelection: null,
    focusTarget: null,
    interactionGuard: null,
  });
  useUIStore.getState().setViewOption('showCollision', false);
  useUIStore.getState().setDetailLinkTab('visual');
  useUIStore.getState().setPanelSection('property_editor_link_inertial', true);
});

test('parent-joint attention uses exact component ownership with duplicate local IDs', () => {
  const workspace = createWorkspace();
  assert.deepEqual(
    resolveParentJointAttentionSelection(workspace, {
      type: 'link',
      componentId: 'right',
      entityId: 'tool',
    }),
    {
      entity: { type: 'joint', componentId: 'right', entityId: 'wrist' },
    },
  );
});

test('geometry selection preserves collision index only for the exact EntityRef', () => {
  const workspace = createWorkspace();
  useSelectionStore.getState().setSelection({
    entity: { type: 'link', componentId: 'left', entityId: 'tool' },
    subType: 'collision',
    objectIndex: 3,
  });
  const selected: { current: WorkspaceSelection } = { current: null };
  const hook = renderHook(workspace, {
    setSelection: (value) => {
      selected.current = value;
    },
  });

  hook.handleSelect({
    entity: { type: 'link', componentId: 'left', entityId: 'tool' },
    subType: 'collision',
  });
  assert.equal(selected.current?.objectIndex, 3);

  hook.handleSelect({
    entity: { type: 'link', componentId: 'right', entityId: 'tool' },
    subType: 'collision',
  });
  assert.equal(selected.current?.objectIndex, undefined);
  assert.equal(useUIStore.getState().viewOptions.showCollision, true);
});

test('viewer selection pulses the exact parent joint and helper selections update UI', () => {
  const workspace = createWorkspace();
  const pulsed: { current: WorkspaceSelection } = { current: null };
  const hook = renderHook(workspace, {
    pulseSelection: (selection) => {
      pulsed.current = selection;
    },
  });

  hook.handleViewerSelect({
    entity: { type: 'link', componentId: 'right', entityId: 'tool' },
  });
  assert.deepEqual(pulsed.current, {
    entity: { type: 'joint', componentId: 'right', entityId: 'wrist' },
  });

  hook.handleViewerSelect({
    entity: { type: 'link', componentId: 'left', entityId: 'tool' },
    helperKind: 'center-of-mass',
  });
  assert.equal(useUIStore.getState().detailLinkTab, 'physics');
});

test('pending transform blocks selection while focus and hover keep explicit refs', () => {
  const workspace = createWorkspace();
  const transformPendingRef = { current: true };
  const selected: { current: WorkspaceSelection } = { current: null };
  const hook = renderHook(workspace, {
    transformPendingRef,
    setSelection: (value) => {
      selected.current = value;
    },
  });
  const ref = { type: 'link', componentId: 'right', entityId: 'tool' } as const;

  hook.handleSelect({ entity: ref });
  assert.equal(selected.current, null);

  transformPendingRef.current = false;
  hook.handleHover({ entity: ref, subType: 'visual' });
  hook.handleFocus(ref);
  assert.deepEqual(useSelectionStore.getState().hoveredSelection, {
    entity: ref,
    subType: 'visual',
  });
  assert.deepEqual(useSelectionStore.getState().focusTarget, ref);
});

import assert from 'node:assert/strict';
import test from 'node:test';

import { createAttachedChildLink } from '@/core/robot';
import type { InteractionSelection, UrdfJoint, UrdfLink } from '@/types';

import { resolveIkToolLinkOptions } from '../hooks/useIkToolController';
import { resolveIkToolSelectionState } from './ikToolSelectionState';

const links: Record<string, UrdfLink> = {
  base_link: createAttachedChildLink({
    id: 'base_link',
    name: 'base_link',
  }),
  fixed_link: createAttachedChildLink({
    id: 'fixed_link',
    name: 'fixed_link',
  }),
  tool_link: createAttachedChildLink({
    id: 'tool_link',
    name: 'tool_link',
  }),
};

const joints: Record<string, UrdfJoint> = {
  fixed_joint: {
    id: 'fixed_joint',
    name: 'fixed_joint',
    type: 'fixed',
    parentLinkId: 'base_link',
    childLinkId: 'fixed_link',
    origin: {
      xyz: { x: 0, y: 0, z: 0.2 },
      rpy: { r: 0, p: 0, y: 0 },
    },
  } as UrdfJoint,
  tool_joint: {
    id: 'tool_joint',
    name: 'tool_joint',
    type: 'revolute',
    parentLinkId: 'base_link',
    childLinkId: 'tool_link',
    axis: { x: 0, y: 0, z: 1 },
    origin: {
      xyz: { x: 0, y: 0, z: 0.5 },
      rpy: { r: 0, p: 0, y: 0 },
    },
    limit: {
      lower: -1.57,
      upper: 1.57,
      effort: 100,
      velocity: 10,
    },
  } as UrdfJoint,
};

test('resolveIkToolSelectionState stays idle without a link selection', () => {
  assert.deepEqual(
    resolveIkToolSelectionState({
      selection: null,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    {
      status: 'idle',
      currentLinkId: null,
      selectedLinkId: null,
    },
  );
});

test('resolveIkToolSelectionState reports a selected IK link when the clicked link is draggable', () => {
  const selection = {
    type: 'link',
    id: 'tool_link',
  } as InteractionSelection;

  assert.deepEqual(
    resolveIkToolSelectionState({
      selection,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    {
      status: 'selected',
      currentLinkId: 'tool_link',
      selectedLinkId: 'tool_link',
    },
  );
});

test('resolveIkToolSelectionState flags the root link as non-draggable', () => {
  const selection = {
    type: 'link',
    id: 'base_link',
  } as InteractionSelection;

  assert.deepEqual(
    resolveIkToolSelectionState({
      selection,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    {
      status: 'root_not_draggable',
      currentLinkId: 'base_link',
      selectedLinkId: null,
    },
  );
});

test('resolveIkToolSelectionState flags fixed-only links as having no variable chain', () => {
  const selection = {
    type: 'link',
    id: 'fixed_link',
  } as InteractionSelection;

  assert.deepEqual(
    resolveIkToolSelectionState({
      selection,
      ikDragActive: true,
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    {
      status: 'no_variable_chain',
      currentLinkId: 'fixed_link',
      selectedLinkId: null,
    },
  );
});

test('resolveIkToolLinkOptions only lists Links with variable parent chains', () => {
  assert.deepEqual(
    resolveIkToolLinkOptions({
      robotLinks: links,
      robotJoints: joints,
      rootLinkId: 'base_link',
    }),
    [{ value: 'tool_link', label: 'tool_link' }],
  );
});

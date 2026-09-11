import assert from 'node:assert/strict';
import test from 'node:test';

import { createSingleComponentWorkspace } from '@/core/robot';
import { DEFAULT_LINK, type AssemblyState, type RobotData } from '@/types';
import { resolveTreeActiveComponent } from './TreeEditor.tsx';

function robot(name: string): RobotData {
  return {
    name,
    rootLinkId: 'base',
    links: { base: { ...DEFAULT_LINK, id: 'base', name: `${name} base` } },
    joints: {},
  };
}

function workspace(): AssemblyState {
  const value = createSingleComponentWorkspace(robot('left source'), {
    componentId: 'left',
    componentName: 'Left display',
    sourceFile: null,
  });
  value.components.right = createSingleComponentWorkspace(robot('right source'), {
    componentId: 'right',
    componentName: 'Right display',
    sourceFile: null,
  }).components.right;
  return value;
}

test('explicit active component wins without inspecting local entity IDs', () => {
  const value = workspace();
  const active = resolveTreeActiveComponent(value, 'left', {
    entity: { type: 'joint', componentId: 'right', entityId: 'same_local_id' },
  });
  assert.equal(active.id, 'left');
});

test('canonical selection scopes the joint panel when no active component is supplied', () => {
  const value = workspace();
  const active = resolveTreeActiveComponent(value, null, {
    entity: { type: 'link', componentId: 'right', entityId: 'base' },
  });
  assert.equal(active.id, 'right');
});

test('empty workspaces fail fast at the tree boundary', () => {
  const value = workspace();
  value.components = {};
  assert.throws(
    () => resolveTreeActiveComponent(value, null, null),
    /non-empty AssemblyState/,
  );
});

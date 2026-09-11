import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  JointType,
  type AssemblyState,
  type WorkspaceSelection,
} from '@/types';

import {
  filterSelectableBridgeComponents,
  isWorkspaceSelectionAllowedForBridge,
  resolveBlockedBridgeComponentId,
  resolveBridgeSelectionTarget,
} from './bridgeSelection.ts';

const identityTransform = () => ({
  position: { x: 0, y: 0, z: 0 },
  rotation: { r: 0, p: 0, y: 0 },
});

function createAssemblyState(): AssemblyState {
  const component = (id: string, name: string) => ({
    id,
    name,
    sourceFile: `${id}.urdf`,
    visible: true,
    transform: identityTransform(),
    robot: {
      name: `robot_${id}`,
      rootLinkId: 'base_link',
      links: {
        base_link: { ...structuredClone(DEFAULT_LINK), id: 'base_link', name: 'base_link' },
        tool_link: { ...structuredClone(DEFAULT_LINK), id: 'tool_link', name: 'tool_link' },
      },
      joints: {
        tool_joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'tool_joint',
          name: 'tool_joint',
          type: JointType.FIXED,
          parentLinkId: 'base_link',
          childLinkId: 'tool_link',
        },
      },
    },
  });

  return {
    name: 'test-assembly',
    transform: identityTransform(),
    components: {
      component_a: component('component_a', 'Component A'),
      component_b: component('component_b', 'Component B'),
    },
    bridges: {},
  };
}

test('bridge link and joint picks resolve through explicit component ownership', () => {
  const workspace = createAssemblyState();

  assert.deepEqual(
    resolveBridgeSelectionTarget(workspace, {
      entity: { type: 'link', componentId: 'component_a', entityId: 'tool_link' },
    }),
    {
      componentId: 'component_a',
      componentName: 'Component A',
      linkId: 'tool_link',
      linkName: 'tool_link',
    },
  );
  assert.deepEqual(
    resolveBridgeSelectionTarget(workspace, {
      entity: { type: 'joint', componentId: 'component_b', entityId: 'tool_joint' },
    }),
    {
      componentId: 'component_b',
      componentName: 'Component B',
      linkId: 'tool_link',
      linkName: 'tool_link',
    },
  );
});

test('duplicate source-local IDs never leak across bridge component owners', () => {
  const workspace = createAssemblyState();
  const selection: WorkspaceSelection = {
    entity: { type: 'link', componentId: 'component_b', entityId: 'base_link' },
  };

  assert.equal(resolveBridgeSelectionTarget(workspace, selection)?.componentId, 'component_b');
  assert.equal(
    resolveBridgeSelectionTarget(workspace, {
      entity: { type: 'link', componentId: 'missing', entityId: 'base_link' },
    }),
    null,
  );
});

test('bridge selection guard rejects the blocked owner and non-link entities', () => {
  const workspace = createAssemblyState();

  assert.equal(
    isWorkspaceSelectionAllowedForBridge(
      workspace,
      { entity: { type: 'link', componentId: 'component_a', entityId: 'base_link' } },
      'component_a',
    ),
    false,
  );
  assert.equal(
    isWorkspaceSelectionAllowedForBridge(
      workspace,
      { entity: { type: 'link', componentId: 'component_b', entityId: 'base_link' } },
      'component_a',
    ),
    true,
  );
  assert.equal(
    isWorkspaceSelectionAllowedForBridge(
      workspace,
      { entity: { type: 'component', componentId: 'component_b' } },
      'component_a',
    ),
    false,
  );
});

test('bridge helper rules block the opposite side and filter dropdown components', () => {
  const workspace = createAssemblyState();

  assert.equal(
    resolveBlockedBridgeComponentId({
      pickTarget: 'child',
      parentComponentId: 'component_a',
      childComponentId: '',
    }),
    'component_a',
  );
  assert.deepEqual(
    filterSelectableBridgeComponents(
      Object.values(workspace.components),
      'component_a',
    ).map((component) => component.id),
    ['component_b'],
  );
});

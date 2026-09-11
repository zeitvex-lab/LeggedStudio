import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_JOINT, DEFAULT_LINK, JointType, type AssemblyState } from '@/types';

import { resolveWorkspaceRobotDataTarget } from './workspaceRobotTarget.ts';

const identityTransform = () => ({
  position: { x: 0, y: 0, z: 0 },
  rotation: { r: 0, p: 0, y: 0 },
});

function createWorkspace(): AssemblyState {
  const component = (id: string) => ({
    id,
    name: id,
    sourceFile: `${id}.urdf`,
    transform: identityTransform(),
    visible: true,
    robot: {
      name: `${id}_robot`,
      rootLinkId: 'base',
      links: {
        base: { ...structuredClone(DEFAULT_LINK), id: 'base', name: 'authored_base' },
      },
      joints: {},
    },
  });

  return {
    name: 'workspace',
    transform: identityTransform(),
    components: {
      left: component('left'),
      right: component('right'),
    },
    bridges: {
      mount: {
        id: 'mount',
        name: 'mount',
        parentComponentId: 'left',
        parentLinkId: 'base',
        childComponentId: 'right',
        childLinkId: 'base',
        joint: {
          ...structuredClone(DEFAULT_JOINT),
          id: 'mount',
          name: 'mount',
          type: JointType.FIXED,
          parentLinkId: 'base',
          childLinkId: 'base',
        },
      },
    },
  };
}

test('component-owned selections resolve duplicate local IDs without scanning other components', () => {
  const workspace = createWorkspace();
  const target = resolveWorkspaceRobotDataTarget(workspace, {
    entity: { type: 'link', componentId: 'right', entityId: 'base' },
  });

  assert.equal(target.scope, 'component');
  assert.equal(target.componentId, 'right');
  assert.equal(target.robotData, workspace.components.right!.robot);
  assert.deepEqual(target.resolveSnapshotEntityRef('link', 'base'), {
    type: 'link',
    componentId: 'right',
    entityId: 'base',
  });
  assert.equal(target.resolveSnapshotEntityRef('link', 'left_base'), null);
});

test('assembly and bridge selections use the global read-only projection', () => {
  const workspace = createWorkspace();
  const assemblyTarget = resolveWorkspaceRobotDataTarget(workspace, {
    entity: { type: 'assembly' },
  });
  const bridgeTarget = resolveWorkspaceRobotDataTarget(workspace, {
    entity: { type: 'bridge', bridgeId: 'mount' },
  });

  assert.equal(assemblyTarget.scope, 'assembly');
  assert.equal(bridgeTarget.scope, 'assembly');
  assert.ok(assemblyTarget.robotData.links.left_base);
  assert.ok(assemblyTarget.robotData.links.right_base);
  assert.deepEqual(assemblyTarget.resolveSnapshotEntityRef('link', 'right_base'), {
    type: 'link',
    componentId: 'right',
    entityId: 'base',
  });
});

test('a single-component overview stays source-local unless assembly is explicitly selected', () => {
  const workspace = createWorkspace();
  delete workspace.bridges.mount;
  delete workspace.components.right;

  assert.equal(resolveWorkspaceRobotDataTarget(workspace, null).scope, 'component');
  assert.equal(
    resolveWorkspaceRobotDataTarget(workspace, { entity: { type: 'assembly' } }).scope,
    'assembly',
  );
});

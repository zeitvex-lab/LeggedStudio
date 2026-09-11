import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_JOINT, DEFAULT_LINK, JointType, type AssemblyComponent, type AssemblyState, type RobotData } from '@/types';

import { analyzeAssemblyConnectivity } from './assemblyConnectivity.ts';

const IDENTITY_TRANSFORM = {
  position: { x: 0, y: 0, z: 0 },
  rotation: { r: 0, p: 0, y: 0 },
} as const;

function createRobotData(rootId: string, rootName: string): RobotData {
  return {
    name: rootName,
    rootLinkId: rootId,
    links: {
      [rootId]: {
        ...DEFAULT_LINK,
        id: rootId,
        name: rootName,
      },
    },
    joints: {},
  };
}

function createComponent(id: string, name: string, sourceFile: string, visible = true): AssemblyComponent {
  const rootId = `${id}_base_link`;
  return {
    id,
    name,
    sourceFile,
    visible,
    transform: structuredClone(IDENTITY_TRANSFORM),
    robot: createRobotData(rootId, name),
  };
}

function createAssembly(): AssemblyState {
  return {
    name: 'demo_workspace',
    transform: structuredClone(IDENTITY_TRANSFORM),
    components: {
      comp_left: createComponent('comp_left', 'left_arm', 'robots/left_arm.urdf'),
      comp_right: createComponent('comp_right', 'right_arm', 'robots/right_arm.urdf'),
    },
    bridges: {},
  };
}

test('analyzeAssemblyConnectivity reports disconnected groups for isolated workspace components', () => {
  const analysis = analyzeAssemblyConnectivity(createAssembly());

  assert.equal(analysis.componentCount, 2);
  assert.equal(analysis.connectedGroupCount, 2);
  assert.equal(analysis.isSingleConnectedComponent, false);
  assert.equal(analysis.hasDisconnectedComponents, true);
  assert.deepEqual(
    analysis.connectedGroups.map((group) => group.componentIds),
    [['comp_left'], ['comp_right']],
  );
});

test('analyzeAssemblyConnectivity treats bridged components as a single exportable assembly', () => {
  const assembly = createAssembly();
  assembly.bridges.bridge_main = {
    id: 'bridge_main',
    name: 'bridge_main',
    parentComponentId: 'comp_left',
    parentLinkId: 'comp_left_base_link',
    childComponentId: 'comp_right',
    childLinkId: 'comp_right_base_link',
    joint: {
      ...DEFAULT_JOINT,
      id: 'bridge_main_joint',
      name: 'bridge_main_joint',
      type: JointType.FIXED,
      parentLinkId: 'comp_left_base_link',
      childLinkId: 'comp_right_base_link',
    },
  };

  const analysis = analyzeAssemblyConnectivity(assembly);

  assert.equal(analysis.connectedGroupCount, 1);
  assert.equal(analysis.isSingleConnectedComponent, true);
  assert.equal(analysis.hasDisconnectedComponents, false);
  assert.deepEqual(
    analysis.connectedGroups.map((group) => group.componentIds),
    [['comp_left', 'comp_right']],
  );
});

test('analyzeAssemblyConnectivity keeps hidden components in disconnected export analysis', () => {
  const assembly = createAssembly();
  assembly.components.comp_right.visible = false;

  const analysis = analyzeAssemblyConnectivity(assembly);

  assert.equal(analysis.componentCount, 2);
  assert.equal(analysis.connectedGroupCount, 2);
  assert.equal(analysis.hasDisconnectedComponents, true);
});

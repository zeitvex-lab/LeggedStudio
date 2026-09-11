import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createAssemblyScenePlacement,
  createAssemblySceneProjection,
  createSingleComponentWorkspace,
} from '@/core/robot';
import { DEFAULT_JOINT, DEFAULT_LINK, JointType, type AssemblyState, type BridgeJoint } from '@/types';

import { buildBridgePreviewWorkspace } from './bridgePreviewWorkspace.ts';

function createWorkspace(): AssemblyState {
  const workspace = createSingleComponentWorkspace({
    name: 'shared',
    rootLinkId: 'base',
    links: { base: { ...structuredClone(DEFAULT_LINK), id: 'base', name: 'base' } },
    joints: {},
  }, { componentId: 'parent' });
  workspace.components.child = {
    ...structuredClone(workspace.components.parent!),
    id: 'child',
    name: 'child',
    sourceFile: 'child.urdf',
    transform: {
      position: { x: 2, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
  };
  return workspace;
}

function createPreview(): BridgeJoint {
  return {
    id: '__bridge_preview__',
    name: 'preview',
    parentComponentId: 'parent',
    parentLinkId: 'base',
    childComponentId: 'child',
    childLinkId: 'base',
    joint: {
      ...structuredClone(DEFAULT_JOINT),
      id: '__bridge_preview__',
      name: 'preview',
      type: JointType.FIXED,
      parentLinkId: 'base',
      childLinkId: 'base',
    },
  };
}

test('bridge preview changes only a read-only scene workspace and canonical mappings stay explicit', () => {
  const workspace = createWorkspace();
  const snapshot = structuredClone(workspace);
  const previewWorkspace = buildBridgePreviewWorkspace(workspace, createPreview());
  const projection = createAssemblySceneProjection(previewWorkspace);
  const placement = createAssemblyScenePlacement(previewWorkspace, projection);

  assert.notEqual(previewWorkspace, workspace);
  assert.ok(previewWorkspace.bridges.__bridge_preview__);
  assert.deepEqual(workspace, snapshot);
  assert.deepEqual(projection.globalToEntityRef.get('__bridge_preview__'), {
    type: 'bridge',
    bridgeId: '__bridge_preview__',
  });
  assert.ok(placement.robotData.joints.__bridge_preview__);
});

test('closing bridge preview restores the canonical workspace reference', () => {
  const workspace = createWorkspace();
  assert.equal(buildBridgePreviewWorkspace(workspace, null), workspace);
});

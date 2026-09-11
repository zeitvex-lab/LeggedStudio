import assert from 'node:assert/strict';
import test from 'node:test';

import { createAssemblySceneProjection, createSingleComponentWorkspace } from '@/core/robot';
import { DEFAULT_LINK, type RobotData, type RobotFile } from '@/types';

import { resolveCanonicalWorkspaceViewerDocument } from './canonicalWorkspaceViewerDocument.ts';

function robot(name: string): RobotData {
  return {
    name,
    rootLinkId: 'base',
    links: { base: { ...structuredClone(DEFAULT_LINK), id: 'base', name: 'base' } },
    joints: {},
  };
}

test('hydrated USD direct component never exposes a USD renderer source', () => {
  const workspace = createSingleComponentWorkspace(robot('hydrated'), {
    componentId: 'usd_component',
    sourceFile: 'robots/hydrated.usd',
  });
  const source: RobotFile = {
    name: 'robots/hydrated.usd',
    format: 'usd',
    content: '#usda 1.0',
  };
  const document = resolveCanonicalWorkspaceViewerDocument({
    workspace,
    projection: createAssemblySceneProjection(workspace),
    availableFiles: [source],
    componentSourceDrafts: {},
  });

  assert.equal(document.synthetic, true);
  assert.equal(document.sourceFile.format, 'urdf');
  assert.equal(document.sourceFormat, 'urdf');
  assert.notEqual(document.sourceFile.name, source.name);
});

test('assembled scene always uses synthetic structured URDF context', () => {
  const workspace = createSingleComponentWorkspace(robot('first'), {
    componentId: 'first',
    sourceFile: 'first.mjcf',
  });
  workspace.components.second = {
    ...structuredClone(workspace.components.first!),
    id: 'second',
    name: 'second',
    sourceFile: 'second.urdf',
  };
  const document = resolveCanonicalWorkspaceViewerDocument({
    workspace,
    projection: createAssemblySceneProjection(workspace),
    availableFiles: [
      { name: 'first.mjcf', format: 'mjcf', content: '<mujoco />' },
      { name: 'second.urdf', format: 'urdf', content: '<robot />' },
    ],
    componentSourceDrafts: {},
  });

  assert.equal(document.synthetic, true);
  assert.equal(document.sourceFile.format, 'urdf');
  assert.equal(document.componentId, null);
});

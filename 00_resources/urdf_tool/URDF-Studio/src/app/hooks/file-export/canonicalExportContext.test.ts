import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createComponentSourceDraft,
  createSingleComponentWorkspace,
} from '@/core/robot';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  GeometryType,
  JointType,
  type ComponentSourceFormat,
  type RobotData,
} from '@/types';

import {
  buildCanonicalExportContext,
  buildCanonicalWorkspaceExportAssets,
  collectCanonicalWorkspacePreparedMeshFiles,
} from './canonicalExportContext.ts';

function robot(name = 'source_robot'): RobotData {
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
        type: JointType.FIXED,
        parentLinkId: 'base',
        childLinkId: 'tool',
      },
    },
  };
}

for (const format of ['urdf', 'mjcf', 'sdf', 'xacro', 'usd'] as const) {
  test(`identity ${format.toUpperCase()} component preserves its matching owned draft and source name`, () => {
    const workspace = createSingleComponentWorkspace(robot(), {
      componentId: 'component',
      sourceFile: `library/source-name.${format}`,
    });
    const draft = createComponentSourceDraft({
      componentId: 'component',
      format: format as ComponentSourceFormat,
      content: `owned-${format}-source`,
      robot: workspace.components.component!.robot,
    });

    const context = buildCanonicalExportContext({
      workspace,
      componentSourceDrafts: { component: draft },
    });

    assert.equal(context.exportName, 'source-name');
    assert.equal(context.sourceFile?.format, format);
    assert.equal(context.sourceFile?.content, `owned-${format}-source`);
    assert.deepEqual(Object.keys(context.robot.links), ['base', 'tool']);
  });
}

test('stale draft is rejected instead of falling back to library content', () => {
  const workspace = createSingleComponentWorkspace(robot(), {
    componentId: 'component',
    sourceFile: 'library/template.urdf',
  });
  const draft = createComponentSourceDraft({
    componentId: 'component',
    format: 'urdf',
    content: 'stale-owned-source',
    robot: workspace.components.component!.robot,
  });
  workspace.components.component!.robot.links.tool!.name = 'mutated';

  const context = buildCanonicalExportContext({
    workspace,
    componentSourceDrafts: { component: draft },
  });

  assert.equal(context.sourceFile, null);
  assert.equal(context.exportName, 'template');
});

test('fresh owned source with sourceFile=null preserves content under a stable generated name', () => {
  const workspace = createSingleComponentWorkspace(robot('draft robot'), {
    componentId: 'component',
    sourceFile: null,
  });
  const draft = createComponentSourceDraft({
    componentId: 'component',
    format: 'xacro',
    content: '<robot xmlns:xacro="http://www.ros.org/wiki/xacro" />',
    robot: workspace.components.component!.robot,
  });
  const context = buildCanonicalExportContext({
    workspace,
    componentSourceDrafts: { component: draft },
  });

  assert.equal(context.sourceFile?.name, 'draft_robot.urdf.xacro');
  assert.equal(context.sourceFile?.format, 'xacro');
  assert.equal(context.exportName, 'draft_robot');
});

test('missing draft still preserves the identity component source filename for generated export', () => {
  const workspace = createSingleComponentWorkspace(robot('renamed robot'), {
    componentId: 'component',
    sourceFile: 'original/source-name.sdf',
  });
  const context = buildCanonicalExportContext({
    workspace,
    componentSourceDrafts: {},
  });

  assert.equal(context.sourceFile, null);
  assert.equal(context.exportName, 'source-name');
});

test('single transforms use canonical placement and disable source preservation', () => {
  const workspace = createSingleComponentWorkspace(robot(), {
    componentId: 'component',
    sourceFile: 'source.urdf',
  });
  const draft = createComponentSourceDraft({
    componentId: 'component',
    format: 'urdf',
    content: '<robot />',
    robot: workspace.components.component!.robot,
  });
  workspace.components.component!.transform.position.x = 2;

  const context = buildCanonicalExportContext({
    workspace,
    componentSourceDrafts: { component: draft },
  });

  assert.equal(context.identityComponent, null);
  assert.equal(context.sourceFile, null);
  assert.notEqual(context.robot.rootLinkId, 'base');
  assert.ok(
    Object.values(context.robot.joints).some((joint) => joint.origin.xyz.x === 2),
  );
});

test('same-source multi instances and bridges generate one disambiguated canonical projection', () => {
  const workspace = createSingleComponentWorkspace(robot('left'), {
    componentId: 'left',
    sourceFile: 'shared.urdf',
  });
  workspace.components.right = {
    ...structuredClone(workspace.components.left!),
    id: 'right',
    name: 'right',
    robot: robot('right'),
  };
  workspace.bridges.mount = {
    id: 'mount',
    name: 'mount',
    parentComponentId: 'left',
    parentLinkId: 'tool',
    childComponentId: 'right',
    childLinkId: 'base',
    joint: {
      ...structuredClone(DEFAULT_JOINT),
      id: 'mount',
      name: 'mount',
      type: JointType.FIXED,
      parentLinkId: 'tool',
      childLinkId: 'base',
    },
  };

  const context = buildCanonicalExportContext({
    workspace,
    componentSourceDrafts: {},
  });

  assert.equal(context.sourceFile, null);
  assert.ok(context.robot.links.left_base);
  assert.ok(context.robot.links.right_base);
  assert.ok(context.robot.joints.mount);
});

test('multi-USD prepared mesh files use the same component resource namespace as projection', () => {
  const workspace = createSingleComponentWorkspace(robot('left'), {
    componentId: 'left',
    sourceFile: 'robots/left.usd',
  });
  workspace.components.right = createSingleComponentWorkspace(robot('right'), {
    componentId: 'right',
    sourceFile: 'robots/right.usd',
  }).components.right;
  Object.values(workspace.components).forEach((component) => {
    component.robot.links.base!.visual = {
      ...component.robot.links.base!.visual,
      type: GeometryType.MESH,
      meshPath: 'base_link_visual_0.obj',
    };
  });
  const leftBlob = new Blob(['left']);
  const rightBlob = new Blob(['right']);
  const context = buildCanonicalExportContext({ workspace, componentSourceDrafts: {} });
  const meshFiles = collectCanonicalWorkspacePreparedMeshFiles({
    workspace,
    getPreparedCache: (sourceFile) => ({
      stageSourcePath: sourceFile,
      robotData: workspace.components[sourceFile.includes('left') ? 'left' : 'right']!.robot,
      meshFiles: {
        'base_link_visual_0.obj': sourceFile.includes('left') ? leftBlob : rightBlob,
      },
    }),
  });
  const projectedPaths = [
    context.robot.links.left_base!.visual.meshPath,
    context.robot.links.right_base!.visual.meshPath,
  ];

  assert.notEqual(projectedPaths[0], projectedPaths[1]);
  assert.deepEqual(new Set(meshFiles.keys()), new Set(projectedPaths as string[]));
  assert.equal(meshFiles.get(projectedPaths[0]!), leftBlob);
  assert.equal(meshFiles.get(projectedPaths[1]!), rightBlob);
});

test('multi-component non-USD export aliases projected mesh and texture resources', () => {
  const workspace = createSingleComponentWorkspace(robot('left'), {
    componentId: 'left',
    sourceFile: 'robots/left/model.urdf',
  });
  workspace.components.right = createSingleComponentWorkspace(robot('right'), {
    componentId: 'right',
    sourceFile: 'robots/right/model.sdf',
  }).components.right;
  Object.values(workspace.components).forEach((component) => {
    component.robot.links.base!.visual = {
      ...component.robot.links.base!.visual,
      type: GeometryType.MESH,
      meshPath: 'meshes/body.obj',
      authoredMaterials: [{ texture: 'textures/body.png' }],
    };
  });
  const context = buildCanonicalExportContext({ workspace, componentSourceDrafts: {} });
  const exportAssets = buildCanonicalWorkspaceExportAssets({
    workspace,
    assets: {
      'robots/left/meshes/body.obj': 'blob:left-mesh',
      'robots/left/textures/body.png': 'blob:left-texture',
      'robots/right/meshes/body.obj': 'blob:right-mesh',
      'robots/right/textures/body.png': 'blob:right-texture',
    },
  });
  const leftVisual = context.robot.links.left_base!.visual;
  const rightVisual = context.robot.links.right_base!.visual;

  assert.equal(exportAssets[leftVisual.meshPath!], 'blob:left-mesh');
  assert.equal(exportAssets[rightVisual.meshPath!], 'blob:right-mesh');
  assert.equal(
    exportAssets[leftVisual.authoredMaterials![0]!.texture!],
    'blob:left-texture',
  );
  assert.equal(
    exportAssets[rightVisual.authoredMaterials![0]!.texture!],
    'blob:right-texture',
  );
  assert.notEqual(leftVisual.meshPath, rightVisual.meshPath);
});

test('assembled non-USD export aliases relative assets for a source-less component', () => {
  const workspace = createSingleComponentWorkspace(robot('local'), {
    componentId: 'local',
    sourceFile: null,
  });
  workspace.components.peer = createSingleComponentWorkspace(robot('peer'), {
    componentId: 'peer',
    sourceFile: 'robots/peer.urdf',
  }).components.peer;
  workspace.components.local!.robot.links.base!.visual = {
    ...workspace.components.local!.robot.links.base!.visual,
    type: GeometryType.MESH,
    meshPath: 'meshes/local.obj',
    authoredMaterials: [{ texture: 'textures/local.png' }],
  };

  const context = buildCanonicalExportContext({ workspace, componentSourceDrafts: {} });
  const exportAssets = buildCanonicalWorkspaceExportAssets({
    workspace,
    assets: {
      'meshes/local.obj': 'blob:local-mesh',
      'textures/local.png': 'blob:local-texture',
    },
  });
  const localVisual = context.robot.links.local_base!.visual;

  assert.equal(exportAssets[localVisual.meshPath!], 'blob:local-mesh');
  assert.equal(
    exportAssets[localVisual.authoredMaterials![0]!.texture!],
    'blob:local-texture',
  );
});

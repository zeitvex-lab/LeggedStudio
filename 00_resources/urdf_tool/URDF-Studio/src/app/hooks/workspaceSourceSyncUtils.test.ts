import assert from 'node:assert/strict';
import test from 'node:test';

import { createSingleComponentWorkspace } from '@/core/robot';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  type RobotData,
  type RobotFile,
  type RobotState,
} from '@/types';

import {
  buildGeneratedWorkspaceUrdfFileName,
  buildPreviewSceneSourceFromImportResult,
  createGeneratedWorkspaceUrdfFile,
  createPreviewRobotStateFromImportResult,
  createRobotSourceSnapshot,
  createWorkspaceGeneratedRobotSnapshot,
  isGeneratedWorkspaceUrdfFileName,
  resolveWorkspaceGeneratedUrdfRobotData,
  shouldPromptGenerateWorkspaceUrdfOnStructureSwitch,
} from './workspaceSourceSyncUtils.ts';

function createRobot(name = 'demo'): RobotData {
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

function createRobotState(name = 'demo'): RobotState {
  return {
    ...createRobot(name),
    selection: { type: null, id: null },
  };
}

test('createRobotSourceSnapshot ignores selection and object insertion order', () => {
  const first = createRobotState();
  const second: RobotState = {
    ...first,
    links: {
      tool: first.links.tool!,
      base: first.links.base!,
    },
    selection: { type: 'joint', id: 'wrist' },
  };

  assert.equal(createRobotSourceSnapshot(first), createRobotSourceSnapshot(second));
});

test('generated workspace filenames stay reserved, sanitized, and collision-safe', () => {
  const files: RobotFile[] = [
    { name: 'generated/My_Robot.generated.urdf', format: 'urdf', content: '' },
  ];

  assert.equal(
    buildGeneratedWorkspaceUrdfFileName({
      assemblyName: ' My Robot ',
      availableFiles: files,
    }),
    'generated/My_Robot_2.generated.urdf',
  );
  assert.equal(isGeneratedWorkspaceUrdfFileName('/generated/My_Robot.generated.urdf'), true);
  assert.equal(isGeneratedWorkspaceUrdfFileName('library/My_Robot.urdf'), false);
});

test('createGeneratedWorkspaceUrdfFile emits a selection-free projection and semantic baseline', () => {
  const currentRobot = createRobot('workspace_robot');

  const result = createGeneratedWorkspaceUrdfFile({
    assemblyName: 'Workspace',
    mergedRobotData: currentRobot,
    availableFiles: [],
  });

  assert.equal(result.file.name, 'generated/Workspace.generated.urdf');
  assert.match(result.file.content, /<robot name="workspace_robot">/);
  assert.deepEqual(result.robot.selection, { type: null, id: null });

  const withTransientMotion = structuredClone(result.robot);
  withTransientMotion.joints.wrist!.angle = 0.75;
  const { selection: _selection, ...withTransientMotionData } = withTransientMotion;
  assert.equal(
    result.snapshot,
    createWorkspaceGeneratedRobotSnapshot(
      createSingleComponentWorkspace(withTransientMotionData, { componentId: 'arm' }),
    ),
  );
});

test('generated source derives from canonical workspace transforms, never selected source state', () => {
  const workspace = createSingleComponentWorkspace(createRobot(), { componentId: 'arm' });
  const baselineSnapshot = createWorkspaceGeneratedRobotSnapshot(workspace);

  assert.equal(
    shouldPromptGenerateWorkspaceUrdfOnStructureSwitch({
      assemblyState: workspace,
      baselineSnapshot,
    }),
    false,
  );

  workspace.components.arm!.transform.position.x = 2;
  const transformedRobot = resolveWorkspaceGeneratedUrdfRobotData({ assemblyState: workspace });

  assert.notEqual(transformedRobot.rootLinkId, 'base');
  assert.ok(Object.values(transformedRobot.joints).some((joint) => joint.origin.xyz.x === 2));
  assert.equal(
    shouldPromptGenerateWorkspaceUrdfOnStructureSwitch({
      assemblyState: workspace,
      baselineSnapshot,
    }),
    true,
  );
});

test('joint motion is transient for generated-workspace change detection', () => {
  const workspace = createSingleComponentWorkspace(createRobot(), { componentId: 'arm' });
  const baselineSnapshot = createWorkspaceGeneratedRobotSnapshot(workspace);

  workspace.components.arm!.robot.joints.wrist!.angle = 1.25;

  assert.equal(
    shouldPromptGenerateWorkspaceUrdfOnStructureSwitch({
      assemblyState: workspace,
      baselineSnapshot,
    }),
    false,
  );
});

test('preview state is derived from a ready import result or a USD hydration placeholder', () => {
  const urdfFile: RobotFile = {
    name: 'demo.urdf',
    format: 'urdf',
    content: '<robot name="demo"><link name="base"/></robot>',
  };
  const ready = {
    status: 'ready' as const,
    format: 'urdf' as const,
    robotData: createRobot(),
    resolvedUrdfContent: urdfFile.content,
    resolvedUrdfSourceFilePath: urdfFile.name,
  };
  const readyPreview = createPreviewRobotStateFromImportResult(urdfFile, ready);

  assert.deepEqual(readyPreview?.selection, { type: null, id: null });
  assert.equal(
    buildPreviewSceneSourceFromImportResult(urdfFile, {
      availableFiles: [urdfFile],
      previewRobot: readyPreview,
      importResult: ready,
    }),
    urdfFile.content,
  );

  const usdFile: RobotFile = { name: 'scene.usd', format: 'usd', content: '' };
  const hydration = { status: 'needs_hydration' as const, format: 'usd' as const };
  const usdPreview = createPreviewRobotStateFromImportResult(usdFile, hydration);

  assert.equal(usdPreview?.rootLinkId, 'usd_scene_root');
  assert.equal(
    buildPreviewSceneSourceFromImportResult(usdFile, {
      availableFiles: [usdFile],
      previewRobot: usdPreview,
      importResult: hydration,
    }),
    '',
  );
});

test('source-only MJCF fragments are intentionally omitted from file preview', () => {
  const file: RobotFile = {
    name: 'fragment.xml',
    format: 'mjcf',
    content: '<body name="fragment"/>',
  };
  const importResult = {
    status: 'error' as const,
    format: 'mjcf' as const,
    reason: 'source_only_fragment' as const,
  };

  assert.equal(createPreviewRobotStateFromImportResult(file, importResult), null);
  assert.equal(
    buildPreviewSceneSourceFromImportResult(file, {
      availableFiles: [file],
      previewRobot: null,
      importResult,
    }),
    null,
  );
});

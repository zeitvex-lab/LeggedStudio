import assert from 'node:assert/strict';
import test from 'node:test';

import JSZip from 'jszip';
import { JSDOM } from 'jsdom';

import { parseURDF } from '@/core/parsers';
import {
  createComponentSourceDraft,
  createDefaultWorkspace,
  createSingleComponentWorkspace,
} from '@/core/robot';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  JointType,
  type AssemblyState,
  type ComponentSourceDraft,
  type RobotData,
  type WorkspaceHistory,
} from '@/types';
import {
  PROJECT_ASSET_MANIFEST_FILE,
  PROJECT_COMPONENT_SOURCE_DRAFTS_FILE,
  PROJECT_MANIFEST_FILE,
  PROJECT_VERSION,
  PROJECT_WORKSPACE_HISTORY_FILE,
  PROJECT_WORKSPACE_STATE_FILE,
} from './projectArchive';
import {
  exportProject,
  type ExportProjectParams,
  type ProjectExportProgress,
} from './projectExport';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;

function createRobot(name = 'demo', rootLinkId = 'base_link'): RobotData {
  return {
    name,
    rootLinkId,
    links: {
      [rootLinkId]: {
        ...DEFAULT_LINK,
        id: rootLinkId,
        name: rootLinkId,
        visible: true,
      },
    },
    joints: {},
  };
}

function createHistory(overrides: Partial<WorkspaceHistory> = {}): WorkspaceHistory {
  return {
    past: [],
    future: [],
    activity: [],
    ...overrides,
  };
}

function createExportParams({
  workspace,
  sourceFiles = {},
  assetUrls = {},
  workspaceHistory = createHistory(),
  componentSourceDrafts,
  onProgress,
}: {
  workspace: AssemblyState;
  sourceFiles?: Record<string, string>;
  assetUrls?: Record<string, string>;
  workspaceHistory?: WorkspaceHistory;
  componentSourceDrafts?: Record<string, ComponentSourceDraft>;
  onProgress?: (progress: ProjectExportProgress) => void;
}): ExportProjectParams {
  const availableFiles = Object.entries(sourceFiles).map(([name, content]) => ({
    name,
    content,
    format: 'urdf' as const,
  }));
  const selectedFileName = availableFiles[0]?.name ?? null;
  return {
    name: workspace.name,
    lang: 'en',
    workspace,
    workspaceHistory,
    componentSourceDrafts,
    assets: {
      availableFiles,
      assetUrls,
      allFileContents: { ...sourceFiles },
      motorLibrary: {},
      selectedFileName,
    },
    derivedCaches: { usdPreparedExportCaches: {} },
    onProgress,
  };
}

async function exportToZip(params: ExportProjectParams): Promise<JSZip> {
  const result = await exportProject(params);
  assert.equal(result.partial, false);
  assert.deepEqual(result.warnings, []);
  return JSZip.loadAsync(await result.blob.arrayBuffer());
}

test('exportProject writes only the canonical .usp 3.0 workspace timeline', async () => {
  const sourcePath = 'robots/demo.urdf';
  const sourceContent = '<robot name="demo"><link name="base_link" /></robot>';
  const workspace = createSingleComponentWorkspace(createRobot(), {
    workspaceName: 'demo_project',
    componentId: 'robot_1',
    sourceFile: sourcePath,
  });
  const pastWorkspace = structuredClone(workspace);
  pastWorkspace.name = 'before_rename';
  const workspaceHistory = createHistory({
    past: [pastWorkspace],
    activity: [{
      id: 'rename_1',
      timestamp: '2026-07-09T12:00:00.000Z',
      label: 'Renamed workspace',
    }],
  });

  const zip = await exportToZip(createExportParams({
    workspace,
    sourceFiles: { [sourcePath]: sourceContent },
    workspaceHistory,
  }));

  assert.ok(zip.file(PROJECT_MANIFEST_FILE));
  assert.ok(zip.file(PROJECT_WORKSPACE_STATE_FILE));
  assert.ok(zip.file(PROJECT_WORKSPACE_HISTORY_FILE));
  assert.ok(zip.file(PROJECT_ASSET_MANIFEST_FILE));
  assert.equal(zip.file('project.json'), null);
  assert.equal(zip.file('history/robot.json'), null);
  assert.equal(zip.file('history/assembly.json'), null);

  const manifest = JSON.parse(await zip.file(PROJECT_MANIFEST_FILE)!.async('string'));
  assert.deepEqual(Object.keys(manifest).sort(), ['entries', 'metadata', 'version']);
  assert.equal(manifest.version, PROJECT_VERSION);
  assert.equal(manifest.entries.workspace, PROJECT_WORKSPACE_STATE_FILE);
  assert.equal(manifest.entries.workspaceHistory, PROJECT_WORKSPACE_HISTORY_FILE);
  assert.equal('ui' in manifest, false);
  assert.equal('assembly' in manifest, false);
  assert.equal('robot' in manifest, false);

  const archivedWorkspace = JSON.parse(
    await zip.file(PROJECT_WORKSPACE_STATE_FILE)!.async('string'),
  );
  const archivedHistory = JSON.parse(
    await zip.file(PROJECT_WORKSPACE_HISTORY_FILE)!.async('string'),
  );
  assert.deepEqual(archivedWorkspace, workspace);
  assert.deepEqual(archivedHistory, workspaceHistory);
  assert.equal('present' in archivedHistory, false);
});

test('exportProject accepts the canonical source-less blank workspace', async () => {
  const workspace = createDefaultWorkspace('blank_project');
  const zip = await exportToZip(createExportParams({ workspace }));

  const archivedWorkspace = JSON.parse(
    await zip.file(PROJECT_WORKSPACE_STATE_FILE)!.async('string'),
  );
  assert.equal(archivedWorkspace.components.component_1.sourceFile, null);
  assert.ok(zip.file('components/component_1/state.json'));
  assert.ok(zip.file('output/blank_project.urdf'));
});

test('exportProject preserves committed joint motion in workspace and undo history', async () => {
  const robot = createRobot('motion_robot');
  robot.links.tool_link = {
    ...DEFAULT_LINK,
    id: 'tool_link',
    name: 'tool_link',
    visible: true,
  };
  robot.joints.hinge = {
    ...DEFAULT_JOINT,
    id: 'hinge',
    name: 'hinge',
    type: JointType.REVOLUTE,
    parentLinkId: 'base_link',
    childLinkId: 'tool_link',
    angle: 0.75,
    quaternion: { x: 0, y: 0, z: 0.1, w: 0.995 },
  };
  const workspace = createSingleComponentWorkspace(robot, {
    workspaceName: 'motion_project',
    componentId: 'motion',
  });
  const past = structuredClone(workspace);
  past.components.motion.robot.joints.hinge.angle = -0.25;
  const future = structuredClone(workspace);
  future.components.motion.robot.joints.hinge.angle = 1.25;
  const zip = await exportToZip(createExportParams({
    workspace,
    workspaceHistory: createHistory({ past: [past], future: [future] }),
  }));

  const archivedWorkspace = JSON.parse(
    await zip.file(PROJECT_WORKSPACE_STATE_FILE)!.async('string'),
  );
  const archivedHistory = JSON.parse(
    await zip.file(PROJECT_WORKSPACE_HISTORY_FILE)!.async('string'),
  );
  assert.equal(archivedWorkspace.components.motion.robot.joints.hinge.angle, 0.75);
  assert.deepEqual(
    archivedWorkspace.components.motion.robot.joints.hinge.quaternion,
    robot.joints.hinge.quaternion,
  );
  assert.equal(archivedHistory.past[0].components.motion.robot.joints.hinge.angle, -0.25);
  assert.equal(archivedHistory.future[0].components.motion.robot.joints.hinge.angle, 1.25);
});

test('exportProject validates canonical state before attempting asset IO', async () => {
  const invalidWorkspace = createDefaultWorkspace('invalid');
  invalidWorkspace.components = {};

  await assert.rejects(
    exportProject(createExportParams({
      workspace: invalidWorkspace,
      assetUrls: { 'missing.png': 'blob:missing' },
    })),
    /canonical workspace.*components.*at least one component/i,
  );
});

test('exportProject rejects session state instead of archiving it', async () => {
  const workspace = createDefaultWorkspace('session_leak');
  (workspace as unknown as Record<string, unknown>).activeComponentId = 'component_1';

  await assert.rejects(
    exportProject(createExportParams({ workspace })),
    /activeComponentId.*(?:session state|canonical workspace field)/i,
  );
});

test('exportProject fails fast when a packed asset cannot be fetched', async () => {
  const workspace = createDefaultWorkspace('broken_asset_project');

  await assert.rejects(
    exportProject(createExportParams({
      workspace,
      assetUrls: { 'textures/missing.png': 'blob:missing-project-asset' },
    })),
    /Failed to pack asset "textures\/missing\.png"/,
  );
});

test('exportProject applies workspace and component transforms to generated output', async () => {
  const sourcePath = 'robots/arm.urdf';
  const sourceContent = '<robot name="arm"><link name="base_link" /></robot>';
  const workspace = createSingleComponentWorkspace(createRobot('arm'), {
    workspaceName: 'transformed_workspace',
    componentId: 'arm_1',
    sourceFile: sourcePath,
    workspaceTransform: {
      position: { x: 1, y: 2, z: 3 },
      rotation: { r: 0.1, p: -0.2, y: 0.3 },
    },
    componentTransform: {
      position: { x: -0.5, y: 0.25, z: 0.75 },
      rotation: { r: -0.15, p: 0.35, y: -0.45 },
    },
  });
  const zip = await exportToZip(createExportParams({
    workspace,
    sourceFiles: { [sourcePath]: sourceContent },
  }));

  const output = await zip.file('output/arm.urdf')?.async('string');
  assert.ok(output);
  const robot = parseURDF(output);
  assert.ok(robot);
  const workspaceRootJoint = Object.values(robot.joints).find(
    (joint) => joint.parentLinkId === robot.rootLinkId,
  );
  const componentRootJoint = Object.values(robot.joints).find(
    (joint) => joint.childLinkId === 'base_link',
  );
  assert.deepEqual(workspaceRootJoint?.origin.xyz, workspace.transform.position);
  assert.deepEqual(
    componentRootJoint?.origin.xyz,
    workspace.components.arm_1.transform.position,
  );
});

test('exportProject keeps bridge quaternion metadata as a derived artifact', async () => {
  const leftSource = 'robots/left.urdf';
  const rightSource = 'robots/right.urdf';
  const workspace = createSingleComponentWorkspace(createRobot('left', 'left_base_link'), {
    workspaceName: 'bridge_workspace',
    componentId: 'left',
    sourceFile: leftSource,
  });
  workspace.components.right = createSingleComponentWorkspace(
    createRobot('right', 'right_base_link'), {
    componentId: 'right',
    sourceFile: rightSource,
    },
  ).components.right;
  workspace.bridges.mount = {
    id: 'mount',
    name: 'mount',
    parentComponentId: 'left',
    parentLinkId: 'left_base_link',
    childComponentId: 'right',
    childLinkId: 'right_base_link',
    joint: {
      ...DEFAULT_JOINT,
      id: 'mount',
      name: 'mount_joint',
      type: JointType.FIXED,
      parentLinkId: 'left_base_link',
      childLinkId: 'right_base_link',
      origin: {
        xyz: { x: 1.25, y: -2.5, z: 3.75 },
        rpy: { r: 0.1, p: -0.2, y: 0.3 },
        quatXyzw: { x: 0, y: 0, z: 0.70710678, w: 0.70710678 },
      },
    },
  };
  const source = '<robot name="robot"><link name="base_link" /></robot>';
  const zip = await exportToZip(createExportParams({
    workspace,
    sourceFiles: { [leftSource]: source, [rightSource]: source },
  }));

  const bridgeXml = await zip.file('bridges/bridge.xml')?.async('string');
  assert.ok(bridgeXml);
  assert.match(bridgeXml, /xyz="1\.25 -2\.5 3\.75"/);
  assert.match(bridgeXml, /rpy="0\.1 -0\.2 0\.3"/);
  assert.match(bridgeXml, /quat_xyzw="0 0 0\.70710678 0\.70710678"/);

  const output = await zip.file('output/bridge_workspace.urdf')?.async('string');
  assert.ok(output);
  const exportedRobot = parseURDF(output);
  assert.ok(exportedRobot);
  const exportedBridge = Object.values(exportedRobot.joints).find(
    (joint) => joint.name === workspace.bridges.mount.id,
  );
  assert.ok(exportedBridge);
  assert.deepEqual(exportedBridge.origin.xyz, workspace.bridges.mount.joint.origin.xyz);
  assert.deepEqual(exportedBridge.origin.rpy, workspace.bridges.mount.joint.origin.rpy);
});

test('exportProject archives only fresh component-owned source drafts without library fallback', async () => {
  const sourcePath = 'robots/demo.urdf';
  const sourceContent = '<robot name="demo"><link name="base_link" /></robot>';
  const workspace = createSingleComponentWorkspace(createRobot(), {
    componentId: 'demo-instance',
    sourceFile: sourcePath,
  });
  const draft = createComponentSourceDraft({
    componentId: 'demo-instance',
    format: 'urdf',
    content: sourceContent,
    robot: workspace.components['demo-instance'].robot,
  });
  const zip = await exportToZip(createExportParams({
    workspace,
    componentSourceDrafts: { 'demo-instance': draft },
  }));
  const manifest = JSON.parse(await zip.file(PROJECT_MANIFEST_FILE)!.async('string'));
  assert.equal(manifest.entries.componentSourceDrafts, PROJECT_COMPONENT_SOURCE_DRAFTS_FILE);
  const draftManifest = JSON.parse(
    await zip.file(PROJECT_COMPONENT_SOURCE_DRAFTS_FILE)!.async('string'),
  );
  assert.deepEqual(draftManifest.drafts.map((entry: { componentId: string }) => entry.componentId), [
    'demo-instance',
  ]);
  assert.equal(
    await zip.file(draftManifest.drafts[0].contentPath)!.async('string'),
    sourceContent,
  );

  workspace.components['demo-instance'].robot.name = 'semantic-edit';
  const staleZip = await exportToZip(createExportParams({
    workspace,
    componentSourceDrafts: { 'demo-instance': draft },
  }));
  const staleManifest = JSON.parse(
    await staleZip.file(PROJECT_MANIFEST_FILE)!.async('string'),
  );
  assert.equal(staleManifest.entries.componentSourceDrafts, undefined);
  assert.equal(staleZip.file(PROJECT_COMPONENT_SOURCE_DRAFTS_FILE), null);
});

test('exportProject skips USD source drafts because binary source and prepared cache own USD roundtrip', async () => {
  const workspace = createSingleComponentWorkspace(createRobot('usd_robot'), {
    componentId: 'usd-instance',
    sourceFile: 'robots/usd_robot.usd',
  });
  const usdDraft = createComponentSourceDraft({
    componentId: 'usd-instance',
    format: 'usd',
    content: '#usda 1.0',
    robot: workspace.components['usd-instance'].robot,
  });
  const zip = await exportToZip(createExportParams({
    workspace,
    componentSourceDrafts: { 'usd-instance': usdDraft },
  }));
  const manifest = JSON.parse(await zip.file(PROJECT_MANIFEST_FILE)!.async('string'));
  assert.equal(manifest.entries.componentSourceDrafts, undefined);
  assert.equal(zip.file(PROJECT_COMPONENT_SOURCE_DRAFTS_FILE), null);
});

test('exportProject reports all archive phases', async () => {
  const progress: ProjectExportProgress[] = [];
  await exportProject(createExportParams({
    workspace: createDefaultWorkspace('progress_project'),
    assetUrls: { 'textures/progress.png': 'data:text/plain;base64,cHJvZ3Jlc3M=' },
    onProgress: (update) => progress.push(update),
  }));

  const phases = new Set(progress.map((update) => update.phase));
  assert.deepEqual(
    Array.from(phases).sort(),
    ['archive', 'assets', 'components', 'metadata', 'output'],
  );
  assert.ok(progress.every(({ completed, total }) => total > 0 && completed <= total));
});

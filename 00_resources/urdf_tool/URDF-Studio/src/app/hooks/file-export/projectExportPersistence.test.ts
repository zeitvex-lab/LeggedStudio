import assert from 'node:assert/strict';
import test, { beforeEach } from 'node:test';

import { createSingleComponentWorkspace } from '@/core/robot';
import { translations } from '@/shared/i18n';
import { useWorkspaceStore } from '@/store/workspaceStore';
import {
  DEFAULT_JOINT,
  DEFAULT_LINK,
  JointType,
  type RobotData,
} from '@/types';
import { registerPendingHistoryFlusher } from '@/app/utils/pendingHistory';

import { createExportProgressReporter, replaceTemplate } from './progress.ts';
import { executeProjectExport } from './projectExport.ts';
import {
  captureProjectExportPersistenceSnapshot,
  isProjectExportPersistenceSnapshotCurrent,
} from './projectExportPersistence.ts';

function robot(): RobotData {
  return {
    name: 'export_robot',
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
        type: JointType.REVOLUTE,
        parentLinkId: 'base',
        childLinkId: 'tool',
      },
    },
  };
}

beforeEach(() => {
  const current = useWorkspaceStore.getState();
  if (current.transaction) {
    current.cancelWorkspaceTransaction(current.transaction.id);
  }
  current.flushPendingJointMotion({ skipHistory: true });
  current.replaceWorkspace(
    createSingleComponentWorkspace(robot(), {
      componentId: 'component',
      sourceFile: 'export.urdf',
      workspaceName: 'before export',
    }),
    { resetHistory: true },
  );
  useWorkspaceStore.setState({
    history: { past: [], future: [], activity: [] },
  });
});

test('project capture flushes a pending property transaction before cloning workspace history', () => {
  const store = useWorkspaceStore.getState();
  const operationId = store.beginWorkspaceTransaction('Rename before project export');
  assert.equal(
    store.renameWorkspace('pending property value', { operationId }),
    true,
  );
  let flushCount = 0;
  const unregister = registerPendingHistoryFlusher(() => {
    flushCount += 1;
    useWorkspaceStore.getState().commitWorkspaceTransaction(operationId);
  });

  try {
    const capture = captureProjectExportPersistenceSnapshot();

    assert.equal(flushCount, 1);
    assert.equal(useWorkspaceStore.getState().transaction, null);
    assert.equal(capture.workspace.name, 'pending property value');
    assert.equal(capture.workspaceHistory.past.length, 1);
    assert.equal(capture.workspaceHistory.past[0]?.name, 'before export');
    assert.equal(
      capture.workspaceHistory.activity.at(-1)?.label,
      'Rename before project export',
    );
  } finally {
    unregister();
  }
});

test('project capture commits pending joint motion exactly once into workspace history', () => {
  const store = useWorkspaceStore.getState();
  assert.equal(
    store.setJointMotion(
      { type: 'joint', componentId: 'component', entityId: 'wrist' },
      0.75,
    ),
    true,
  );
  assert.equal(useWorkspaceStore.getState().history.past.length, 0);

  const capture = captureProjectExportPersistenceSnapshot();

  assert.equal(
    capture.workspace.components.component?.robot.joints.wrist?.angle,
    0.75,
  );
  assert.equal(capture.workspaceHistory.past.length, 1);
  assert.equal(useWorkspaceStore.getState().history.past.length, 1);
  assert.equal(useWorkspaceStore.getState().flushPendingJointMotion(), false);
});

test('project capture owns immutable workspace and history snapshots', () => {
  const capture = captureProjectExportPersistenceSnapshot();
  useWorkspaceStore.getState().renameWorkspace('edited after capture');

  assert.equal(capture.workspace.name, 'before export');
  assert.equal(capture.workspaceHistory.past.length, 0);
  assert.equal(
    isProjectExportPersistenceSnapshotCurrent(capture),
    false,
  );
});

test('a concurrent workspace mutation during archive build cannot mark the project saved', async () => {
  const capture = captureProjectExportPersistenceSnapshot();
  let finishArchive: (() => void) | null = null;
  let archivedWorkspaceName: string | null = null;
  let markSavedCount = 0;

  const execution = executeProjectExport({
    options: { skipDownload: true },
    name: capture.workspace.name,
    lang: 'en',
    workspace: capture.workspace,
    workspaceHistory: capture.workspaceHistory,
    componentSourceDrafts: {},
    assets: {
      availableFiles: [],
      assetUrls: {},
      allFileContents: {},
      motorLibrary: {},
      selectedFileName: null,
    },
    createProgressReporter: (onProgress, totalSteps) =>
      createExportProgressReporter(onProgress, totalSteps),
    downloadBlob: () => {},
    replaceTemplate,
    t: translations.en,
    markAllSaved: () => {
      markSavedCount += 1;
    },
    isPersistenceSnapshotCurrent: () =>
      isProjectExportPersistenceSnapshotCurrent(capture),
    archiveProject: async (params) => {
      archivedWorkspaceName = params.workspace.name;
      await new Promise<void>((resolve) => {
        finishArchive = resolve;
      });
      return { blob: new Blob(['project']), partial: false, warnings: [] };
    },
  });

  await Promise.resolve();
  assert.equal(archivedWorkspaceName, 'before export');
  useWorkspaceStore.getState().renameWorkspace('concurrent edit');
  assert.ok(finishArchive);
  const resolveArchive = finishArchive as unknown as () => void;
  resolveArchive();
  await execution;

  assert.equal(markSavedCount, 0);
  assert.equal(archivedWorkspaceName, 'before export');
  assert.equal(useWorkspaceStore.getState().workspace.name, 'concurrent edit');
});

test('an unchanged archived persistence snapshot is marked saved once', async () => {
  const capture = captureProjectExportPersistenceSnapshot();
  let markSavedCount = 0;

  await executeProjectExport({
    options: { skipDownload: true },
    name: capture.workspace.name,
    lang: 'en',
    workspace: capture.workspace,
    workspaceHistory: capture.workspaceHistory,
    componentSourceDrafts: {},
    assets: {
      availableFiles: [],
      assetUrls: {},
      allFileContents: {},
      motorLibrary: {},
      selectedFileName: null,
    },
    createProgressReporter: (onProgress, totalSteps) =>
      createExportProgressReporter(onProgress, totalSteps),
    downloadBlob: () => {},
    replaceTemplate,
    t: translations.en,
    markAllSaved: () => {
      markSavedCount += 1;
    },
    isPersistenceSnapshotCurrent: () =>
      isProjectExportPersistenceSnapshotCurrent(capture),
    archiveProject: async () => ({
      blob: new Blob(['project']),
      partial: false,
      warnings: [],
    }),
  });

  assert.equal(markSavedCount, 1);
});

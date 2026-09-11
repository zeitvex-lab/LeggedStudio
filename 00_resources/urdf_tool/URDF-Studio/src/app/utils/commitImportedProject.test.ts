import assert from 'node:assert/strict';
import test, { beforeEach } from 'node:test';

import type { ProjectImportResult } from '@/features/file-io';
import { createComponentSourceDraft, createDefaultWorkspace } from '@/core/robot';
import { useAssetsStore } from '@/store/assetsStore';
import { useSelectionStore } from '@/store/selectionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';

import { commitImportedProject } from './commitImportedProject.ts';

function createResult(): ProjectImportResult {
  const workspace = createDefaultWorkspace('imported');
  workspace.components.component_1!.sourceFile = 'imported.urdf';
  const componentSourceDrafts = {
    component_1: createComponentSourceDraft({
      componentId: 'component_1',
      format: 'urdf',
      content: '<robot />',
      robot: workspace.components.component_1!.robot,
    }),
  };
  return {
    manifest: {
      version: '3.0',
      metadata: { name: 'imported', lastModified: '2026-07-09T00:00:00.000Z' },
      entries: {
        workspace: 'workspace/state.json',
        workspaceHistory: 'history/workspace.json',
        assets: 'assets/manifest.json',
        allFileContents: 'library/all-file-contents.json',
        motorLibrary: 'library/motor-library.json',
      },
    },
    workspace,
    workspaceHistory: {
      past: [],
      future: [],
      activity: [{
        id: 'activity_imported',
        timestamp: '2026-07-09T00:00:00.000Z',
        label: 'Imported edit',
      }],
    },
    componentSourceDrafts,
    assets: {
      assetUrls: { 'meshes/body.stl': 'blob:imported-body' },
      availableFiles: [{ name: 'imported.urdf', format: 'urdf', content: '<robot />' }],
      allFileContents: { 'imported.urdf': '<robot />' },
      motorLibrary: {},
      selectedFileName: 'imported.urdf',
    },
    derivedCaches: { usdPreparedExportCaches: {} },
    warnings: [],
  };
}

beforeEach(() => {
  useWorkspaceStore.getState().replaceWorkspace(createDefaultWorkspace('before'), {
    resetHistory: true,
  });
  useWorkspaceStore.setState({ history: { past: [], future: [], activity: [] } });
  useAssetsStore.setState({
    assets: { 'old.stl': 'https://example.invalid/old.stl' },
    availableFiles: [{ name: 'before.urdf', format: 'urdf', content: '<before />' }],
    selectedFile: null,
    allFileContents: { 'before.urdf': '<before />' },
  });
  useSelectionStore.setState({ selection: null });
});

test('validated project restore commits canonical workspace, history, assets, and selection', () => {
  let markedSaved = 0;
  const selected = commitImportedProject(createResult(), {
    markWorkspaceBaselineSaved: () => {
      markedSaved += 1;
    },
  });

  assert.equal(selected?.name, 'imported.urdf');
  assert.equal(useWorkspaceStore.getState().workspace.name, 'imported');
  assert.equal(
    useWorkspaceStore.getState().history.activity[0]?.label,
    'Imported edit',
  );
  assert.deepEqual(useAssetsStore.getState().assets, {
    'meshes/body.stl': 'blob:imported-body',
  });
  assert.equal(
    useAssetsStore.getState().componentSourceDrafts.component_1?.content,
    '<robot />',
  );
  assert.deepEqual(useSelectionStore.getState().selection, null);
  assert.equal(markedSaved, 1);
});

test('workspace validation failure leaves workspace, history, and assets untouched', () => {
  const beforeWorkspace = structuredClone(useWorkspaceStore.getState().workspace);
  const beforeHistory = structuredClone(useWorkspaceStore.getState().history);
  const beforeAssets = structuredClone(useAssetsStore.getState().assets);
  const beforeDrafts = structuredClone(useAssetsStore.getState().componentSourceDrafts);
  const beforeRevision = useWorkspaceStore.getState().revision;
  const result = createResult();
  result.workspace.components = {};

  assert.throws(() => commitImportedProject(result), /canonical workspace/i);
  assert.deepEqual(useWorkspaceStore.getState().workspace, beforeWorkspace);
  assert.deepEqual(useWorkspaceStore.getState().history, beforeHistory);
  assert.deepEqual(useAssetsStore.getState().assets, beforeAssets);
  assert.deepEqual(useAssetsStore.getState().componentSourceDrafts, beforeDrafts);
  assert.equal(useWorkspaceStore.getState().revision, beforeRevision);
});

test('post-assets failure rolls back workspace, assets, active component, and selection', () => {
  const beforeWorkspace = structuredClone(useWorkspaceStore.getState().workspace);
  const beforeHistory = structuredClone(useWorkspaceStore.getState().history);
  const beforeAssets = structuredClone(useAssetsStore.getState().assets);
  const beforeActive = useWorkspaceStore.getState().activeComponentId;
  const beforeSelection = {
    entity: { type: 'component', componentId: beforeActive } as const,
  };
  useSelectionStore.setState({ selection: beforeSelection });

  assert.throws(
    () => commitImportedProject(createResult(), {
      markWorkspaceBaselineSaved: () => {
        throw new Error('post-assets failure');
      },
    }),
    /post-assets failure/,
  );

  assert.deepEqual(useWorkspaceStore.getState().workspace, beforeWorkspace);
  assert.deepEqual(useWorkspaceStore.getState().history, beforeHistory);
  assert.equal(useWorkspaceStore.getState().activeComponentId, beforeActive);
  assert.deepEqual(useAssetsStore.getState().assets, beforeAssets);
  assert.deepEqual(useSelectionStore.getState().selection, beforeSelection);
});

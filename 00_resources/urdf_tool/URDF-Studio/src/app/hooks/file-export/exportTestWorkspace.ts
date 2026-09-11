import {
  createComponentSourceDraft,
  createDefaultWorkspace,
  createSingleComponentWorkspace,
  isComponentSourceFormat,
} from '@/core/robot';
import { IDENTITY_ASSEMBLY_TRANSFORM } from '@/core/robot/assemblyTransformUtils';
import { useAssetsStore } from '@/store/assetsStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { AssemblyState, RobotData } from '@/types';

function installMatchingTestDrafts(workspace: AssemblyState): void {
  const assets = useAssetsStore.getState();
  assets.clearComponentSourceDrafts();
  Object.values(workspace.components).forEach((component) => {
    if (!component.sourceFile) return;
    const file = assets.availableFiles.find((candidate) => candidate.name === component.sourceFile);
    if (!file || !isComponentSourceFormat(file.format) || !file.content) return;
    assets.setComponentSourceDraft(createComponentSourceDraft({
      componentId: component.id,
      format: file.format,
      content: file.content,
      robot: component.robot,
    }));
  });
}

function normalizeTestWorkspace(workspace: AssemblyState): AssemblyState {
  const normalized = structuredClone(workspace);
  normalized.transform ??= structuredClone(IDENTITY_ASSEMBLY_TRANSFORM);
  Object.values(normalized.components).forEach((component) => {
    component.sourceFile ??= null;
    component.transform ??= structuredClone(IDENTITY_ASSEMBLY_TRANSFORM);
    component.visible ??= true;
  });
  Object.values(normalized.bridges).forEach((bridge) => {
    bridge.joint.id = bridge.id;
    bridge.joint.parentLinkId = bridge.parentLinkId;
    bridge.joint.childLinkId = bridge.childLinkId;
  });
  return normalized;
}

export function resetExportTestWorkspace(): void {
  const workspace = createDefaultWorkspace('my_robot');
  useWorkspaceStore.getState().replaceWorkspace(workspace, { resetHistory: true });
  useAssetsStore.getState().clearComponentSourceDrafts();
}

export function installExportTestRobot(robot: RobotData, _options?: unknown): void {
  const selectedFile = useAssetsStore.getState().selectedFile;
  const canonicalRobot = structuredClone(robot) as RobotData & { selection?: unknown };
  delete canonicalRobot.selection;
  const workspace = createSingleComponentWorkspace(canonicalRobot, {
    componentId: 'component_1',
    sourceFile: selectedFile?.name ?? null,
  });
  useWorkspaceStore.getState().replaceWorkspace(workspace, { resetHistory: true });
  installMatchingTestDrafts(workspace);
}

export function installExportTestWorkspace(workspace: AssemblyState): void {
  const normalized = normalizeTestWorkspace(workspace);
  useWorkspaceStore.getState().replaceWorkspace(normalized, { resetHistory: true });
  installMatchingTestDrafts(normalized);
}

export function updateExportTestWorkspace(
  update: (workspace: AssemblyState) => AssemblyState,
): void {
  installExportTestWorkspace(update(structuredClone(useWorkspaceStore.getState().workspace)));
}

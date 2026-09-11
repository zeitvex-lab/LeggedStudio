import type {
  AssemblyState,
  ComponentSourceDraft,
  ComponentSourceFormat,
  MotorSpec,
  RobotFile,
  UsdPreparedExportCache,
  WorkspaceHistory,
} from '@/types';

export type ProjectAssetEntry = {
  logicalPath: string;
  archivePath: string;
};

export interface ProjectAssetsManifest {
  availableFiles: Array<Pick<RobotFile, 'name' | 'format'>>;
  selectedFileName: string | null;
  packedFiles: ProjectAssetEntry[];
}

export interface ProjectComponentSourceDraftEntry {
  componentId: string;
  format: ComponentSourceFormat;
  robotSnapshotHash: string;
  contentPath: string;
}

export interface ProjectComponentSourceDraftManifest {
  drafts: ProjectComponentSourceDraftEntry[];
}

export type ProjectExportWarningCode =
  | 'project_mesh_asset_missing'
  | 'project_mesh_package_failed'
  | 'project_asset_pack_failed'
  | 'project_component_mesh_asset_missing'
  | 'project_component_mesh_package_failed';

export interface ProjectExportWarning {
  code: ProjectExportWarningCode;
  message: string;
  context?: Record<string, string>;
}

export type ProjectExportProgressPhase =
  | 'assets'
  | 'metadata'
  | 'components'
  | 'output'
  | 'archive';

export interface ProjectExportProgress {
  phase: ProjectExportProgressPhase;
  completed: number;
  total: number;
  label?: string;
}

export interface ExportProjectResult {
  blob: Blob;
  partial: boolean;
  warnings: ProjectExportWarning[];
}

export interface ProjectManifest {
  version: '3.0';
  metadata: {
    name: string;
    lastModified: string;
  };
  entries: {
    workspace: 'workspace/state.json';
    workspaceHistory: 'history/workspace.json';
    assets: 'assets/manifest.json';
    allFileContents: 'library/all-file-contents.json';
    motorLibrary: 'library/motor-library.json';
    componentSourceDrafts?: 'workspace/component-source-drafts.json';
    usdPreparedExportCaches?: 'workspace/usd-prepared-export-caches.json';
  };
}

export interface ProjectExportAssets {
  availableFiles: RobotFile[];
  assetUrls: Record<string, string>;
  allFileContents: Record<string, string>;
  motorLibrary: Record<string, MotorSpec[]>;
  selectedFileName: string | null;
}

export interface ProjectDerivedCaches {
  usdPreparedExportCaches: Record<string, UsdPreparedExportCache>;
}

export interface ExportProjectParams {
  name: string;
  lang: string;
  workspace: AssemblyState;
  workspaceHistory: WorkspaceHistory;
  componentSourceDrafts?: Record<string, ComponentSourceDraft>;
  assets: ProjectExportAssets;
  derivedCaches?: ProjectDerivedCaches;
  onProgress?: (progress: ProjectExportProgress) => void;
}

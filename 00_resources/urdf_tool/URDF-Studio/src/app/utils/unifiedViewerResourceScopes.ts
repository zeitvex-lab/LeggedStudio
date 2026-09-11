import {
  createStableViewerResourceScope,
  type ViewerResourceScope,
} from '@/features/editor';
import type { RobotFile, RobotMaterialState, UrdfLink } from '@/types';

interface UnifiedViewerFilePreview {
  urdfContent: string;
  fileName: string;
}

interface BuildUnifiedViewerResourceScopesArgs {
  activePreview?: UnifiedViewerFilePreview;
  urdfContent: string;
  sourceFilePath?: string;
  sourceFile?: RobotFile | null;
  assets: Record<string, string>;
  allFileContents?: Record<string, string>;
  availableFiles: RobotFile[];
  viewerRobotLinks?: Record<string, UrdfLink>;
  viewerRobotMaterials?: Record<string, RobotMaterialState>;
  previousViewerResourceScope: ViewerResourceScope | null;
}

export interface UnifiedViewerResourceScopesState {
  effectiveUrdfContent: string;
  effectiveSourceFilePath?: string;
  effectiveSourceFile: RobotFile | null | undefined;
  activeViewportFileName: string | null;
  viewerResourceScope: ViewerResourceScope;
}

export function buildUnifiedViewerResourceScopes({
  activePreview,
  urdfContent,
  sourceFilePath,
  sourceFile,
  assets,
  allFileContents,
  availableFiles,
  viewerRobotLinks,
  viewerRobotMaterials,
  previousViewerResourceScope,
}: BuildUnifiedViewerResourceScopesArgs): UnifiedViewerResourceScopesState {
  const effectiveUrdfContent = activePreview ? activePreview.urdfContent : urdfContent;
  const effectiveSourceFilePath = activePreview ? activePreview.fileName : sourceFilePath;
  const effectiveSourceFile =
    activePreview || !sourceFile
      ? null
      : {
          ...sourceFile,
          content: effectiveUrdfContent,
        };
  const activeViewportFileName =
    activePreview?.fileName ?? effectiveSourceFile?.name ?? effectiveSourceFilePath ?? null;

  const viewerResourceScope = createStableViewerResourceScope(previousViewerResourceScope, {
    assets,
    allFileContents,
    availableFiles,
    sourceFile: effectiveSourceFile,
    sourceFilePath: effectiveSourceFilePath,
    robotLinks: viewerRobotLinks,
    robotMaterials: viewerRobotMaterials,
  });

  return {
    effectiveUrdfContent,
    effectiveSourceFilePath,
    effectiveSourceFile,
    activeViewportFileName,
    viewerResourceScope,
  };
}

import type { RobotFile } from '@/types';
import { USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF } from './usdViewerPlaceholder';

export { USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF } from './usdViewerPlaceholder';

export type ViewerRuntimeSourceFormat = 'auto' | 'urdf' | 'mjcf' | 'sdf' | 'xacro';

export function resolveStandaloneViewerSourceFormat(
  selectedFileFormat: RobotFile['format'] | null | undefined,
  options: {
    renderSelectedUsdFromRobotState?: boolean;
  } = {},
): ViewerRuntimeSourceFormat {
  void options;
  if (selectedFileFormat === 'usd') {
    return 'urdf';
  }

  switch (selectedFileFormat) {
    case 'urdf':
    case 'mjcf':
    case 'sdf':
    case 'xacro':
      return selectedFileFormat;
    default:
      return 'auto';
  }
}

export function resolveStandaloneViewerContent({
  selectedFileFormat,
  selectedFileContent,
  resolvedMjcfSourceContent,
  viewerUrdfContent,
  viewerGeneratedUrdfContent,
}: {
  selectedFileFormat: RobotFile['format'] | null | undefined;
  selectedFileContent?: string | null;
  resolvedMjcfSourceContent?: string | null;
  viewerUrdfContent?: string | null;
  viewerGeneratedUrdfContent?: string | null;
  isSelectedUsdHydrating: boolean;
  renderSelectedUsdFromRobotState?: boolean;
}): string {
  if (selectedFileFormat === 'usd') {
    return USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF;
  }

  if (selectedFileFormat === 'mjcf') {
    return resolvedMjcfSourceContent ?? selectedFileContent ?? '';
  }

  if (selectedFileFormat === 'sdf') {
    return selectedFileContent ?? '';
  }

  return viewerUrdfContent ?? viewerGeneratedUrdfContent ?? '';
}

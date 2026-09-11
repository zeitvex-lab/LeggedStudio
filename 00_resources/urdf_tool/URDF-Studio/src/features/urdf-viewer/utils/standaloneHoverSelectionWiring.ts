import type { RobotFile } from '@/types';
import type { ViewerProps } from '../types';

interface ResolveStandaloneViewerHoverSelectionWiringArgs {
  hoveredSelection?: ViewerProps['hoveredSelection'];
  sourceFormat?: ViewerProps['sourceFormat'] | RobotFile['format'] | null;
  isMeshPreview?: boolean;
}

export interface StandaloneViewerHoverSelectionWiring {
  shouldSubscribeToStoreHoveredSelection: boolean;
  hoverSelectionEnabled: boolean;
}

export function resolveStandaloneViewerHoverSelectionWiring({
  hoveredSelection,
  sourceFormat,
  isMeshPreview = false,
}: ResolveStandaloneViewerHoverSelectionWiringArgs): StandaloneViewerHoverSelectionWiring {
  const shouldSubscribeToStoreHoveredSelection =
    hoveredSelection === undefined && sourceFormat === 'usd' && !isMeshPreview;
  const usesInternalHoverSync = hoveredSelection === undefined && sourceFormat !== 'usd';

  return {
    shouldSubscribeToStoreHoveredSelection,
    // Non-USD scenes mirror hover through RobotModel/HoverSelectionSync instead of
    // an explicit hoveredSelection prop, while USD stages need a concrete hover
    // selection feed. Keep hover on whenever either path is available.
    hoverSelectionEnabled:
      hoveredSelection !== undefined ||
      shouldSubscribeToStoreHoveredSelection ||
      usesInternalHoverSync,
  };
}

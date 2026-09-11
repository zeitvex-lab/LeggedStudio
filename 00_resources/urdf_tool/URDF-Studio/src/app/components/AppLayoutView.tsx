import { AppLayoutViewContent } from './app_layout_view_sections';
import type { AppLayoutViewProps } from './app_layout_view_types';

export function AppLayoutView(props: AppLayoutViewProps) {
  const hasDisplayableViewerRobot =
    Object.keys(props.viewer.sceneProjection.robotData.links ?? {}).length > 1;
  const shouldSuppressDocumentLoadingOverlay =
    Boolean(props.assemblyPreparation.overlay) ||
    (hasDisplayableViewerRobot &&
      props.viewer.documentLoadState.status === 'loading' &&
      props.viewer.documentLoadState.fileName === props.viewer.selectedFile?.name);

  return (
    <AppLayoutViewContent
      {...props}
      shouldSuppressDocumentLoadingOverlay={shouldSuppressDocumentLoadingOverlay}
    />
  );
}

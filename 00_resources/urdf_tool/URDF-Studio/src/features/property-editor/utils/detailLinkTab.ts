import type { AppMode, DetailLinkTab } from '@/types';

export function resolveDetailLinkTabAfterViewerMeshSelect(
  mode: AppMode,
  currentTab: DetailLinkTab,
  objectType: 'visual' | 'collision',
): DetailLinkTab {
  // Viewer geometry picks should always reveal the matching link tab so the
  // property panel follows the user's explicit target across all app modes.
  void mode;
  void currentTab;

  return objectType;
}

export function resolveDetailLinkTabAfterGeometrySelection(
  subType: 'visual' | 'collision',
  currentTab: DetailLinkTab,
): DetailLinkTab {
  void currentTab;

  return subType;
}

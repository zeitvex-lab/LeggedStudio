import type { UrdfLink } from '@/types';

export const WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY = 'urdf_viewer_show_visual_workspace';

type PreferenceListener = () => void;
const preferenceListeners = new Set<PreferenceListener>();

function notifyPreferenceListeners() {
  preferenceListeners.forEach((listener) => listener());
}

export function subscribeToShowVisualPreference(listener: PreferenceListener): () => void {
  preferenceListeners.add(listener);
  return () => {
    preferenceListeners.delete(listener);
  };
}

export function readStoredWorkspaceViewerShowVisualPreference(): boolean | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const saved = window.localStorage.getItem(WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY);
    if (saved === 'true' || saved === '1') {
      return true;
    }
    if (saved === 'false' || saved === '0') {
      return false;
    }
  } catch {
    // Ignore storage read failures and fall back to the live robot visibility state.
  }

  return null;
}

export function persistWorkspaceViewerShowVisualPreference(enabled: boolean) {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.setItem(WORKSPACE_VIEWER_SHOW_VISUAL_STORAGE_KEY, String(enabled));
  } catch {
    // Ignore storage write failures and keep the live session state.
  }

  notifyPreferenceListeners();
}

export function resolveWorkspaceViewerShowVisual({
  robotLinks,
  storedPreference,
}: {
  robotLinks: Record<string, UrdfLink>;
  storedPreference: boolean | null;
}): boolean {
  const hasVisibleLinks = Object.values(robotLinks).some((link) => link.visible !== false);
  if (!hasVisibleLinks) {
    return false;
  }

  return storedPreference ?? true;
}

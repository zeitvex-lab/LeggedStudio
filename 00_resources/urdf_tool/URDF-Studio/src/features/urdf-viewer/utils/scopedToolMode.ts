import type { ToolMode } from '../types';

export interface ScopedToolModeState {
  scopeKey: string | null;
  explicit: boolean;
  mode: ToolMode;
}

export function resolveDefaultViewerToolMode(_sourceFormat?: string | null): ToolMode {
  // Keep default USD loads on the proven interactive path until offscreen
  // rendering matches the existing scene output.
  return 'select';
}

export function createScopedToolModeState(
  scopeKey: string | null,
  defaultMode: ToolMode,
): ScopedToolModeState {
  return {
    scopeKey,
    explicit: false,
    mode: defaultMode,
  };
}

export function resolveScopedToolModeState(
  currentState: ScopedToolModeState,
  scopeKey: string | null,
  defaultMode: ToolMode,
): ScopedToolModeState {
  if (currentState.scopeKey !== scopeKey) {
    return createScopedToolModeState(scopeKey, defaultMode);
  }

  if (!currentState.explicit && currentState.mode !== defaultMode) {
    return createScopedToolModeState(scopeKey, defaultMode);
  }

  return currentState;
}

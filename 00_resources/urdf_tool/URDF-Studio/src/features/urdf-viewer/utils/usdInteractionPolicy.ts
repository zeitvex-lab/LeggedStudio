import type { ToolMode, ViewerInteractiveLayer, ViewerSceneMode } from '../types.ts';
import type { InteractiveGeometrySubType } from './interactionMode.ts';
import { resolvePreferredUsdGeometryRole } from './usdInteractionPicking.ts';

export interface UsdStageInteractionPolicy {
  enableContinuousHover: boolean;
  enableJointRotation: boolean;
  enableMeshSelection: boolean;
}

export interface ResolveUsdStageJointRotationOptions {
  mode: ViewerSceneMode;
  showVisual: boolean;
  showCollision: boolean;
  showCollisionAlwaysOnTop?: boolean;
  interactionLayerPriority?: readonly ViewerInteractiveLayer[];
  toolMode: ToolMode;
}

export interface UsdStageJointRotationRuntime {
  enabled: boolean;
  pickSubType: InteractiveGeometrySubType | null;
}

function isInteractiveSelectionEnabledForToolMode(toolMode: ToolMode): boolean {
  return toolMode !== 'view' && toolMode !== 'face' && toolMode !== 'paint';
}

export function isContinuousHoverEnabledForToolMode(toolMode: ToolMode): boolean {
  return toolMode !== 'view';
}

export function resolveUsdStageInteractionPolicy(
  mode: ViewerSceneMode,
  toolMode: ToolMode = 'select',
): UsdStageInteractionPolicy {
  void mode;
  const enableContinuousHover = isContinuousHoverEnabledForToolMode(toolMode);
  const enableSelection = isInteractiveSelectionEnabledForToolMode(toolMode);

  return {
    enableContinuousHover,
    enableJointRotation: enableSelection,
    enableMeshSelection: enableSelection,
  };
}

export function resolveUsdStageJointRotationRuntime({
  mode,
  showVisual,
  showCollision,
  showCollisionAlwaysOnTop = true,
  interactionLayerPriority,
  toolMode,
}: ResolveUsdStageJointRotationOptions): UsdStageJointRotationRuntime {
  void mode;
  if (toolMode === 'measure' || !isInteractiveSelectionEnabledForToolMode(toolMode)) {
    return {
      enabled: false,
      pickSubType: null,
    };
  }

  const subType = resolvePreferredUsdGeometryRole({
    interactionLayerPriority,
    showVisual,
    showCollision,
    showCollisionAlwaysOnTop,
  });

  if (subType !== 'visual') {
    return {
      enabled: false,
      pickSubType: subType,
    };
  }

  return {
    enabled: true,
    pickSubType: subType,
  };
}

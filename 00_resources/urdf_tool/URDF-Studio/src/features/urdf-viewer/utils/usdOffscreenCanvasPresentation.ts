import { WORKSPACE_CANVAS_BACKGROUND } from '../../../shared/components/3d/scene/constants.ts';

export function resolveUsdOffscreenCanvasPresentation(theme: 'light' | 'dark') {
  return {
    alpha: true,
    backgroundColor: WORKSPACE_CANVAS_BACKGROUND[theme],
    clearAlpha: 0,
    cssBackgroundColor: 'transparent',
    sceneBackgroundColor: null,
  } as const;
}

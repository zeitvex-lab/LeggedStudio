import { isUsdLikeFormat } from '@/core/parsers/usd';

export function shouldMountRobotBeforeAssetsComplete(sourceFormat: 'urdf' | 'mjcf' | 'usd'): boolean {
  void sourceFormat;
  return false;
}

export function shouldForceViewerRuntimeRemount(
  sourceFormat:
    | 'urdf'
    | 'mjcf'
    | 'usd'
    | 'usda'
    | 'xacro'
    | 'sdf'
    | 'mesh'
    | 'asset'
    | null
    | undefined,
): boolean {
  return isUsdLikeFormat(sourceFormat);
}

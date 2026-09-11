import { GeometryType, type RobotState } from '@/types';

import { collectReferencedMeshes } from './assetUtils.ts';

export const USD_EXPORT_WORKER_SUPPORTED_MESH_EXTENSIONS = [
  '.obj',
  '.stl',
  '.msh',
  '.dae',
  '.gltf',
  '.glb',
] as const;

function normalizeMeshExtension(meshPath: string): string {
  const normalized = String(meshPath || '').trim().split(/[?#]/, 1)[0].toLowerCase();
  const extensionIndex = normalized.lastIndexOf('.');
  return extensionIndex >= 0 ? normalized.slice(extensionIndex) : '';
}

export function isUsdExportWorkerSupportedMeshPath(meshPath: string): boolean {
  const extension = normalizeMeshExtension(meshPath);
  return USD_EXPORT_WORKER_SUPPORTED_MESH_EXTENSIONS.includes(
    extension as (typeof USD_EXPORT_WORKER_SUPPORTED_MESH_EXTENSIONS)[number],
  );
}

export function getUsdExportWorkerUnsupportedMeshPaths(robot: RobotState): string[] {
  return Array.from(collectReferencedMeshes(robot.links, GeometryType.MESH))
    .filter((meshPath) => !isUsdExportWorkerSupportedMeshPath(meshPath))
    .sort((left, right) => left.localeCompare(right));
}

export function createUsdExportWorkerUnsupportedMeshError(meshPaths: string[]): Error {
  const [firstMeshPath] = meshPaths;
  const supportedFormats = USD_EXPORT_WORKER_SUPPORTED_MESH_EXTENSIONS
    .map((extension) => extension.slice(1).toUpperCase())
    .join('/');

  return new Error(
    `USD export worker currently supports ${supportedFormats} mesh assets only. `
    + `Found ${meshPaths.length} unsupported mesh asset(s); first unsupported mesh: ${firstMeshPath || 'unknown'}`,
  );
}

export function assertUsdExportWorkerSupport(robot: RobotState): void {
  const unsupportedMeshPaths = getUsdExportWorkerUnsupportedMeshPaths(robot);
  if (unsupportedMeshPaths.length === 0) {
    return;
  }

  throw createUsdExportWorkerUnsupportedMeshError(unsupportedMeshPaths);
}

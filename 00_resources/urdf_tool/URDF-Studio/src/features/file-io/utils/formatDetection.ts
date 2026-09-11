/**
 * Format Detection Utilities
 * Detect robot file format from content and filename
 */

import {
  detectRobotDefinitionFormat,
  isRobotDefinitionPath,
} from '@/core/parsers/format_detection';
import { isMotorLibraryDataFilePath } from '@/shared/data/motorLibrary';
import type { FileFormat } from '../types';

/**
 * Detect file format from content and filename
 * @param content - File content as string
 * @param filename - Filename with extension
 * @returns Detected format or null if unknown
 */
export function detectFormat(content: string, filename: string): FileFormat | null {
  return detectRobotDefinitionFormat(content, filename);
}

/**
 * Check if file is a robot definition file by extension
 */
export function isRobotDefinitionFile(filename: string): boolean {
  return isRobotDefinitionPath(filename);
}

/**
 * Check if file is an asset file (mesh or texture)
 */
export function isAssetFile(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase();
  return [
    'stl',
    'msh',
    'obj',
    'dae',
    'gltf',
    'glb',
    'ply',
    'vtk',
    'bin',
    'png',
    'jpg',
    'jpeg',
    'tga',
    'bmp',
    'tiff',
    'tif',
    'webp',
    'hdr',
  ].includes(ext || '');
}

/**
 * Check if path is a motor library file
 */
export function isMotorLibraryFile(path: string): boolean {
  return isMotorLibraryDataFilePath(path);
}

/**
 * Check if file is a 3D mesh file
 */
export function isMeshFile(filename: string): boolean {
  const ext = filename.split('.').pop()?.toLowerCase();
  return ['stl', 'msh', 'obj', 'dae', 'gltf', 'glb', 'ply', 'vtk'].includes(ext || '');
}

/**
 * Check if path should be skipped (hidden files/folders)
 */
export function shouldSkipPath(path: string): boolean {
  const pathParts = path.split('/');
  return pathParts.some((part) => part.startsWith('.'));
}

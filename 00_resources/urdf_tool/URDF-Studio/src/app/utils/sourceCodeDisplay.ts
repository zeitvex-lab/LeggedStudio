import type { RobotFile } from '../../types/robot.ts';
import type { SourceCodeDocumentFlavor } from '@/features/code-editor';

export type { SourceCodeDocumentFlavor } from '@/features/code-editor';

type SourceCodeFileLike = Pick<RobotFile, 'name' | 'format' | 'content'>;

function hasTextUsdSource(file: SourceCodeFileLike): boolean {
  const normalizedName = file.name.toLowerCase();
  if (normalizedName.endsWith('.usda')) {
    return true;
  }

  return file.content.trimStart().startsWith('#usda');
}

export function shouldUseEquivalentMjcfForUsdSource(
  file: SourceCodeFileLike | null | undefined,
): boolean {
  return Boolean(file && file.format === 'usd' && !hasTextUsdSource(file));
}

export function getSourceCodeDocumentFlavor(
  file: SourceCodeFileLike | null | undefined,
): SourceCodeDocumentFlavor {
  if (!file) {
    return 'urdf';
  }

  if (file.format === 'mjcf') {
    return 'mjcf';
  }

  if (file.format === 'xacro') {
    return 'xacro';
  }

  if (file.format === 'sdf') {
    return 'sdf';
  }

  if (file.format === 'usd') {
    return shouldUseEquivalentMjcfForUsdSource(file) ? 'equivalent-mjcf' : 'usd';
  }

  return 'urdf';
}

export function isSourceCodeDocumentReadOnly(documentFlavor: SourceCodeDocumentFlavor): boolean {
  return documentFlavor === 'usd' || documentFlavor === 'equivalent-mjcf';
}

import type { RobotFile } from '@/types';

interface BuildSimpleModeDraftFileParams {
  selectedFile: RobotFile;
  currentSourceContent: string | null | undefined;
  fallbackUrdfContent: string | null | undefined;
  availableFiles: Pick<RobotFile, 'name'>[];
  now?: Date;
}

const SIMPLE_MODE_DRAFT_SOURCE_FORMATS = new Set<RobotFile['format']>(['urdf', 'sdf']);

function getFileDirectory(fileName: string): string {
  const lastSlashIndex = fileName.lastIndexOf('/');
  return lastSlashIndex === -1 ? '' : fileName.slice(0, lastSlashIndex + 1);
}

function getFileBaseName(fileName: string): string {
  const lastSlashIndex = fileName.lastIndexOf('/');
  return lastSlashIndex === -1 ? fileName : fileName.slice(lastSlashIndex + 1);
}

function stripDraftSourceExtension(fileName: string): string {
  const baseName = getFileBaseName(fileName).trim();
  if (!baseName) {
    return 'robot';
  }

  return (
    baseName.replace(/\.(?:urdf|sdf|mjcf|usd)\.xacro$/i, '').replace(/\.[^./]+$/i, '') || 'robot'
  );
}

function getDraftFileExtension(format: Extract<RobotFile['format'], 'urdf' | 'sdf'>): string {
  return format === 'sdf' ? '.sdf' : '.urdf';
}

function formatDraftTimestamp(date: Date): string {
  const year = String(date.getUTCFullYear()).padStart(4, '0');
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  const day = String(date.getUTCDate()).padStart(2, '0');
  const hours = String(date.getUTCHours()).padStart(2, '0');
  const minutes = String(date.getUTCMinutes()).padStart(2, '0');
  const seconds = String(date.getUTCSeconds()).padStart(2, '0');
  return `${year}${month}${day}-${hours}${minutes}${seconds}`;
}

export function buildSimpleModeDraftFile({
  selectedFile,
  currentSourceContent,
  fallbackUrdfContent,
  availableFiles,
  now = new Date(),
}: BuildSimpleModeDraftFileParams): RobotFile | null {
  const preferredContent = String(currentSourceContent ?? '').trim();
  const fallbackContent = String(fallbackUrdfContent ?? '').trim();
  const canKeepCurrentSourceFormat =
    (selectedFile.format === 'urdf' || selectedFile.format === 'sdf') &&
    preferredContent.length > 0;

  const format: Extract<RobotFile['format'], 'urdf' | 'sdf'> =
    canKeepCurrentSourceFormat && selectedFile.format === 'sdf' ? 'sdf' : 'urdf';
  const content = canKeepCurrentSourceFormat ? preferredContent : fallbackContent;

  if (!content) {
    return null;
  }

  const existingNames = new Set(availableFiles.map((file) => file.name));
  const directory = getFileDirectory(selectedFile.name);
  const stem = stripDraftSourceExtension(selectedFile.name);
  const timestamp = formatDraftTimestamp(now);
  const extension = getDraftFileExtension(format);

  let suffixIndex = 1;
  let candidateName = `${directory}${stem}.draft-${timestamp}${extension}`;
  while (existingNames.has(candidateName)) {
    suffixIndex += 1;
    candidateName = `${directory}${stem}.draft-${timestamp}-${suffixIndex}${extension}`;
  }

  return {
    name: candidateName,
    format,
    content,
  };
}

import type { RobotFile } from '@/types';

export interface GeneratedWorkspaceFileState {
  nextSelectedFile: RobotFile;
  nextAvailableFiles: RobotFile[];
  nextAllFileContents: Record<string, string>;
}

export function buildGeneratedWorkspaceFileState({
  availableFiles,
  allFileContents,
  file,
}: {
  availableFiles: RobotFile[];
  allFileContents: Record<string, string>;
  file: RobotFile;
}): GeneratedWorkspaceFileState {
  const existingFile = availableFiles.find((entry) => entry.name === file.name) ?? null;
  const nextSelectedFile: RobotFile = existingFile ? { ...existingFile, ...file } : file;
  const nextAvailableFiles = existingFile
    ? availableFiles.map((entry) => (entry.name === file.name ? nextSelectedFile : entry))
    : [...availableFiles, nextSelectedFile];

  return {
    nextSelectedFile,
    nextAvailableFiles,
    nextAllFileContents: {
      ...allFileContents,
      [file.name]: file.content,
    },
  };
}

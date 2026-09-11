type RobotFileLike = {
  name: string;
};

interface ResolveViewerJointScopeKeyOptions {
  previewFileName?: string | null;
  sourceFile?: RobotFileLike | null;
  sourceFilePath?: string | null;
  robotName?: string | null;
}

function normalizeScopeSegment(value: string | null | undefined): string | null {
  const normalized = String(value ?? '').trim();
  return normalized.length > 0 ? normalized : null;
}

export function resolveViewerJointScopeKey({
  previewFileName,
  sourceFile,
  sourceFilePath,
  robotName,
}: ResolveViewerJointScopeKeyOptions): string {
  const previewScope = normalizeScopeSegment(previewFileName);
  if (previewScope) {
    return `preview:${previewScope}`;
  }

  // Joint panel state must follow the file entry the user selected, not any
  // derived MJCF source path.
  const selectedFileScope = normalizeScopeSegment(sourceFile?.name);
  if (selectedFileScope) {
    return `current:${selectedFileScope}`;
  }

  const sourcePathScope = normalizeScopeSegment(sourceFilePath);
  if (sourcePathScope) {
    return `current:${sourcePathScope}`;
  }

  return `current:${normalizeScopeSegment(robotName) ?? 'robot'}`;
}

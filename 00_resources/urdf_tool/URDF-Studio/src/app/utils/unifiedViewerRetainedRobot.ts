interface RetainedRobotScopeSource {
  format?: string | null;
  name?: string | null;
}

interface BuildUnifiedViewerRetainedRobotScopeKeyArgs {
  sourceFile?: RetainedRobotScopeSource | null;
  sourceFilePath?: string | null;
  sourceFormat?: string | null;
}

export function buildUnifiedViewerRetainedRobotScopeKey({
  sourceFile,
  sourceFilePath,
  sourceFormat,
}: BuildUnifiedViewerRetainedRobotScopeKeyArgs): string | null {
  const normalizedFormat = String(sourceFile?.format ?? sourceFormat ?? '')
    .trim()
    .toLowerCase();
  if (!normalizedFormat || normalizedFormat === 'usd') {
    return null;
  }

  const normalizedFileName = String(sourceFile?.name ?? '').trim();
  if (normalizedFileName) {
    return `${normalizedFormat}:${normalizedFileName}`;
  }

  const normalizedSourceFilePath = String(sourceFilePath ?? '').trim();
  if (normalizedSourceFilePath) {
    return `${normalizedFormat}:${normalizedSourceFilePath}`;
  }

  return `${normalizedFormat}:__inline__`;
}

export function shouldReuseUnifiedViewerRetainedRobot(
  retainedScopeKey: string | null,
  currentScopeKey: string | null,
): boolean {
  return Boolean(retainedScopeKey && currentScopeKey && retainedScopeKey === currentScopeKey);
}

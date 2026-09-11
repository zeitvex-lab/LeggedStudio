export type LibraryRobotLoadIntent = 'direct' | 'preview' | 'discard';

export type LibraryRobotLoadAction =
  | 'load'
  | 'needs-preview-or-discard-confirm'
  | 'preview'
  | 'blocked';

interface ResolveLibraryRobotLoadActionOptions {
  selectedFileName: string | null | undefined;
  shouldPreviewCurrentState: boolean;
  hasSimpleModeSourceEdits: boolean;
  intent: LibraryRobotLoadIntent;
}

export function resolveLibraryRobotLoadAction({
  selectedFileName,
  shouldPreviewCurrentState,
  hasSimpleModeSourceEdits,
  intent,
}: ResolveLibraryRobotLoadActionOptions): LibraryRobotLoadAction {
  if (intent === 'preview') {
    return 'preview';
  }

  if (intent === 'direct' && shouldPreviewCurrentState) {
    return 'preview';
  }

  const shouldGuardLibraryLoad =
    !shouldPreviewCurrentState && Boolean(selectedFileName) && hasSimpleModeSourceEdits;

  if (!shouldGuardLibraryLoad || intent === 'discard') {
    return 'load';
  }

  if (intent === 'direct') {
    return 'needs-preview-or-discard-confirm';
  }

  if (!selectedFileName) {
    return 'blocked';
  }

  return 'blocked';
}

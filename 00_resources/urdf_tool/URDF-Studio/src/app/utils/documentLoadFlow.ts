import type { LoadingProgressMode, RobotFile } from '@/types';

type DocumentLoadStatus = 'idle' | 'loading' | 'hydrating' | 'ready' | 'error';

interface DocumentLoadStateLike {
  status: DocumentLoadStatus;
  fileName: string | null;
  format?: string | null;
  error?: string | null;
  phase?: string | null;
  message?: string | null;
  progressMode?: LoadingProgressMode | null;
  progressPercent?: number | null;
  loadedCount?: number | null;
  totalCount?: number | null;
}

interface RobotImportResultLike {
  status: 'ready' | 'needs_hydration' | 'error';
  reason?: string;
}

interface StaleViewerDocumentLoadEventInput {
  isPreviewing: boolean;
  activeDocumentFileName: string | null;
  documentLoadState: DocumentLoadStateLike;
}

interface PreserveDocumentLoadProgressInput<TDocumentLoadState extends DocumentLoadStateLike> {
  currentState: TDocumentLoadState;
  nextState: TDocumentLoadState;
}

interface ViewerLoadRegressionAfterReadyInput<TDocumentLoadState extends DocumentLoadStateLike> {
  currentState: TDocumentLoadState;
  nextState: TDocumentLoadState;
}

interface RuntimeRobotReadyDocumentLoadStateInput<
  TDocumentLoadState extends DocumentLoadStateLike,
> {
  activeFile: Pick<RobotFile, 'name' | 'format'> | null;
  currentState: TDocumentLoadState;
}

interface ResolvedMjcfViewerSourceLike {
  content: string | null;
  effectiveFileName: string | null;
}

interface ShouldReuseResolvedMjcfViewerRuntimeInput {
  currentSelectedFile: Pick<RobotFile, 'name' | 'format' | 'content'> | null;
  nextFile: Pick<RobotFile, 'name' | 'format' | 'content'>;
  currentResolvedSource: ResolvedMjcfViewerSourceLike | null;
  nextResolvedSource: ResolvedMjcfViewerSourceLike | null;
}

export function shouldCommitResolvedRobotSelection(
  importResult: RobotImportResultLike,
): importResult is Extract<RobotImportResultLike, { status: 'ready' | 'needs_hydration' }> {
  // Source-only fragments can be inspected, but they must not replace the
  // active viewer document or the runtime will try to load a non-entrypoint.
  return importResult.status === 'ready' || importResult.status === 'needs_hydration';
}

export function shouldIgnoreStaleViewerDocumentLoadEvent({
  isPreviewing,
  activeDocumentFileName,
  documentLoadState,
}: StaleViewerDocumentLoadEventInput): boolean {
  if (isPreviewing || !activeDocumentFileName) {
    return false;
  }

  return (
    (documentLoadState.status === 'loading' || documentLoadState.status === 'hydrating') &&
    Boolean(documentLoadState.fileName) &&
    documentLoadState.fileName !== activeDocumentFileName
  );
}

export function preserveDocumentLoadProgressForSameFile<
  TDocumentLoadState extends DocumentLoadStateLike,
>({
  currentState,
  nextState,
}: PreserveDocumentLoadProgressInput<TDocumentLoadState>): TDocumentLoadState {
  const currentPhase = currentState.phase ?? null;
  const nextPhase = nextState.phase ?? null;
  const currentPhaseIsBootstrap =
    currentPhase === 'checking-path' || currentPhase === 'preparing-scene';
  const nextPhaseIsBootstrap = nextPhase === 'checking-path' || nextPhase === 'preparing-scene';
  const currentStateIsActive =
    currentState.status === 'loading' || currentState.status === 'hydrating';
  const nextStateIsActive = nextState.status === 'loading' || nextState.status === 'hydrating';
  const sameFile =
    Boolean(currentState.fileName) &&
    currentState.fileName === nextState.fileName &&
    (currentState.format ?? null) === (nextState.format ?? null);
  const currentHasAdvancedProgress =
    !currentPhaseIsBootstrap ||
    Boolean(currentState.message) ||
    Number(currentState.progressPercent ?? 0) > 0 ||
    Number(currentState.loadedCount ?? 0) > 0;
  const nextStateWouldResetBootstrapProgress =
    nextPhaseIsBootstrap &&
    !nextState.message &&
    !Number.isFinite(nextState.progressPercent) &&
    !Number.isFinite(nextState.loadedCount) &&
    !Number.isFinite(nextState.totalCount);

  if (
    !sameFile ||
    !currentStateIsActive ||
    !nextStateIsActive ||
    !currentHasAdvancedProgress ||
    !nextStateWouldResetBootstrapProgress
  ) {
    return nextState;
  }

  return {
    ...nextState,
    phase: currentState.phase ?? nextState.phase ?? null,
    message: currentState.message ?? nextState.message ?? null,
    progressMode: currentState.progressMode ?? nextState.progressMode ?? null,
    progressPercent: currentState.progressPercent ?? nextState.progressPercent ?? null,
    loadedCount: currentState.loadedCount ?? nextState.loadedCount ?? null,
    totalCount: currentState.totalCount ?? nextState.totalCount ?? null,
  };
}

export function shouldIgnoreViewerLoadRegressionAfterReadySameFile<
  TDocumentLoadState extends DocumentLoadStateLike,
>({ currentState, nextState }: ViewerLoadRegressionAfterReadyInput<TDocumentLoadState>): boolean {
  const sameFile =
    Boolean(currentState.fileName) &&
    currentState.fileName === nextState.fileName &&
    (currentState.format ?? null) === (nextState.format ?? null);

  return (
    sameFile &&
    currentState.status === 'ready' &&
    (nextState.status === 'loading' || nextState.status === 'hydrating')
  );
}

export function resolveRuntimeRobotReadyDocumentLoadState<
  TDocumentLoadState extends DocumentLoadStateLike,
>({
  activeFile,
  currentState,
}: RuntimeRobotReadyDocumentLoadStateInput<TDocumentLoadState>): TDocumentLoadState | null {
  if (!activeFile || activeFile.format === 'usd') {
    return null;
  }

  const sameFile =
    currentState.fileName === activeFile.name &&
    (currentState.format ?? null) === (activeFile.format ?? null);
  const currentStateIsActive =
    currentState.status === 'loading' || currentState.status === 'hydrating';

  if (!sameFile || !currentStateIsActive) {
    return null;
  }

  return {
    ...currentState,
    status: 'ready',
    fileName: activeFile.name,
    format: activeFile.format,
    error: null,
    phase: 'ready',
    message: null,
    progressMode: 'percent',
    progressPercent: 100,
    loadedCount: null,
    totalCount: null,
  };
}

export function shouldReuseResolvedMjcfViewerRuntime({
  currentSelectedFile,
  nextFile,
  currentResolvedSource,
  nextResolvedSource,
}: ShouldReuseResolvedMjcfViewerRuntimeInput): boolean {
  if (!currentSelectedFile || currentSelectedFile.format !== 'mjcf' || nextFile.format !== 'mjcf') {
    return false;
  }

  const currentEffectiveFileName =
    currentResolvedSource?.effectiveFileName ?? currentSelectedFile.name;
  const nextEffectiveFileName = nextResolvedSource?.effectiveFileName ?? nextFile.name;
  const currentViewerContent = currentResolvedSource?.content ?? currentSelectedFile.content;
  const nextViewerContent = nextResolvedSource?.content ?? nextFile.content;

  return (
    currentEffectiveFileName === nextEffectiveFileName && currentViewerContent === nextViewerContent
  );
}

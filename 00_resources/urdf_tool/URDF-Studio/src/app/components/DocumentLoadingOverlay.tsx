import {
  buildLoadingHudState,
  shouldUseIndeterminateStreamingMeshProgress,
} from '@/shared/components/3d/loadingHudState';
import { LoadingHud } from '@/shared/components/3d/LoadingHud';
import { translations, type Language } from '@/shared/i18n';
import type { DocumentLoadState } from '@/store/assetsStore';
import { resolveDocumentLoadingOverlayPresentation } from './documentLoadingOverlayPresentation';

interface DocumentLoadingOverlayProps {
  state: DocumentLoadState;
  lang: Language;
}

type OverlayProgressMode = Parameters<typeof buildLoadingHudState>[0]['progressMode'];

function shouldRenderDocumentLoadingOverlay(state: DocumentLoadState): boolean {
  return (
    state.status === 'loading' ||
    state.status === 'hydrating' ||
    (state.status === 'error' && Boolean(state.error)) ||
    (state.status === 'ready' && Boolean(state.message))
  );
}

function resolveStageLabel(state: DocumentLoadState, lang: Language): string | null {
  const t = translations[lang];

  if (state.status === 'error') {
    return t.loadingRobotFailed;
  }

  if (state.status === 'ready' && state.message) {
    return t.loadingRobotPreviewUnavailable;
  }

  switch (state.phase) {
    case 'checking-path':
      return t.loadingRobotCheckingPath;
    case 'preloading-dependencies':
      return t.loadingRobotPreloadingDependencies;
    case 'initializing-renderer':
      return t.loadingRobotInitializingRenderer;
    case 'preparing-scene':
      return t.loadingRobotPreparing;
    case 'streaming-meshes':
      return t.loadingRobotStreamingMeshes;
    case 'applying-stage-fixes':
      return t.loadingRobotApplyingStageFixes;
    case 'resolving-metadata':
      return t.loadingRobotResolvingMetadata;
    case 'finalizing-scene':
      return t.loadingRobotFinalizingScene;
    default:
      return null;
  }
}

function resolveOverlayProgressMode({
  state,
  useIndeterminateStreamingProgress,
}: {
  state: DocumentLoadState;
  useIndeterminateStreamingProgress: boolean;
}): OverlayProgressMode {
  if (state.status === 'error' || (state.status === 'ready' && state.message)) {
    return 'percent';
  }

  if (useIndeterminateStreamingProgress) {
    return 'indeterminate';
  }

  return state.progressMode ?? null;
}

function resolveOverlayProgressPercent(state: DocumentLoadState): number | null | undefined {
  if (state.status === 'error') {
    return 0;
  }

  if (state.status === 'ready' && state.message) {
    return 100;
  }

  return state.progressPercent;
}

export function DocumentLoadingOverlay({ state, lang }: DocumentLoadingOverlayProps) {
  if (!shouldRenderDocumentLoadingOverlay(state)) {
    return null;
  }

  const t = translations[lang];
  const presentation = resolveDocumentLoadingOverlayPresentation(state);
  const stageLabel = resolveStageLabel(state, lang);
  const isResultState = state.status === 'error' || state.status === 'ready';
  const useIndeterminateStreamingProgress = shouldUseIndeterminateStreamingMeshProgress({
    phase: state.phase,
    loadedCount: state.loadedCount,
    totalCount: state.totalCount,
  });
  const overlayProgressMode = resolveOverlayProgressMode({
    state,
    useIndeterminateStreamingProgress,
  });
  const progressPercent = resolveOverlayProgressPercent(state);
  const loadingHudState = buildLoadingHudState({
    phase: state.status === 'ready' && state.message ? 'ready' : state.phase,
    progressMode: overlayProgressMode,
    loadedCount: useIndeterminateStreamingProgress ? null : state.loadedCount,
    totalCount: useIndeterminateStreamingProgress ? null : state.totalCount,
    progressPercent,
    fallbackDetail: useIndeterminateStreamingProgress
      ? t.loadingRobotParsingInitialMeshes
      : (stageLabel ?? t.loadingRobotPreparing),
  });
  const detailSource = state.error?.trim() || state.message?.trim() || loadingHudState.detail;
  const detail = detailSource === stageLabel ? '' : detailSource;

  return (
    <div
      className={presentation.overlayClassName}
      aria-busy={state.status === 'loading' || state.status === 'hydrating' ? true : undefined}
    >
      <div className={presentation.hudWrapperClassName}>
        <LoadingHud
          title={t.loadingRobot}
          detail={detail}
          progress={loadingHudState.progress}
          progressMode={loadingHudState.progressMode}
          statusLabel={isResultState ? null : loadingHudState.statusLabel}
          stageLabel={stageLabel}
          delayMs={0}
        />
      </div>
    </div>
  );
}

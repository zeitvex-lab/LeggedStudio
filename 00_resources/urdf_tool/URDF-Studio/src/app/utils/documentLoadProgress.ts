import type { RobotImportProgress } from '@/core/parsers/importRobotFile';
import type { ViewerDocumentLoadEvent } from '@/features/editor';
import type { DocumentLoadState } from '@/store/assetsStore';

type DocumentLoadTrackedFormat = DocumentLoadState['format'];

interface PhaseRange {
  start: number;
  end: number;
}

interface OverlayTargetFileNameInput {
  previewFileName: string | null;
  selectedFileName: string | null;
  suppressDocumentLoadingOverlay?: boolean;
  documentLoadState: Pick<DocumentLoadState, 'fileName' | 'status'>;
}

const NON_USD_VIEWER_PHASE_RANGES: Record<string, PhaseRange> = {
  'preparing-scene': { start: 40, end: 55 },
  'streaming-meshes': { start: 55, end: 90 },
  'finalizing-scene': { start: 90, end: 99 },
  ready: { start: 100, end: 100 },
};

const USD_VIEWER_PHASE_RANGES: Record<string, PhaseRange> = {
  'checking-path': { start: 10, end: 14 },
  'preloading-dependencies': { start: 14, end: 28 },
  'initializing-renderer': { start: 28, end: 45 },
  'streaming-meshes': { start: 45, end: 90 },
  'applying-stage-fixes': { start: 90, end: 94 },
  'resolving-metadata': { start: 94, end: 98 },
  'finalizing-scene': { start: 98, end: 99 },
  ready: { start: 100, end: 100 },
};

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function isUsdFamilyFormat(format: DocumentLoadTrackedFormat): boolean {
  return format === 'usd';
}

function resolveViewerPhaseRange(
  format: DocumentLoadTrackedFormat,
  phase: ViewerDocumentLoadEvent['phase'],
): PhaseRange {
  const phaseRanges = isUsdFamilyFormat(format)
    ? USD_VIEWER_PHASE_RANGES
    : NON_USD_VIEWER_PHASE_RANGES;

  return phaseRanges[phase ?? ''] ?? phaseRanges['finalizing-scene'] ?? { start: 0, end: 100 };
}

function mapProgressPercentToRange(progressPercent: number, range: PhaseRange): number {
  const normalizedPercent = clampPercent(progressPercent) / 100;
  return clampPercent(range.start + normalizedPercent * (range.end - range.start));
}

function mapProgressCountsToRange(
  loadedCount: number,
  totalCount: number,
  range: PhaseRange,
): number | null {
  if (!Number.isFinite(loadedCount) || !Number.isFinite(totalCount) || totalCount <= 0) {
    return null;
  }

  const ratio = Math.max(0, Math.min(1, loadedCount / totalCount));
  return clampPercent(range.start + ratio * (range.end - range.start));
}

export function resolveBootstrapDocumentLoadPhase(
  format: DocumentLoadTrackedFormat,
): NonNullable<ViewerDocumentLoadEvent['phase']> {
  return isUsdFamilyFormat(format) ? 'checking-path' : 'preparing-scene';
}

export function mapRobotImportProgressToDocumentLoadPercent(
  format: DocumentLoadTrackedFormat,
  progress: RobotImportProgress,
): number {
  const range = isUsdFamilyFormat(format) ? { start: 0, end: 10 } : { start: 0, end: 40 };
  return mapProgressPercentToRange(progress.progressPercent ?? 0, range);
}

export function resolveRobotImportCompletedDocumentLoadPercent(
  format: DocumentLoadTrackedFormat,
): number {
  return mapRobotImportProgressToDocumentLoadPercent(format, {
    progressPercent: 100,
    message: null,
  });
}

export function mapViewerDocumentLoadEventToDocumentLoadPercent(
  format: DocumentLoadTrackedFormat,
  event: ViewerDocumentLoadEvent,
): number {
  if (event.status === 'ready') {
    return 100;
  }

  if (event.status === 'error') {
    return 0;
  }

  const range = resolveViewerPhaseRange(format, event.phase);

  if (Number.isFinite(event.progressPercent)) {
    return mapProgressPercentToRange(event.progressPercent ?? 0, range);
  }

  const countProgress = mapProgressCountsToRange(
    event.loadedCount ?? NaN,
    event.totalCount ?? NaN,
    range,
  );
  if (countProgress !== null) {
    return countProgress;
  }

  return range.start;
}

export function resolveDocumentLoadingOverlayTargetFileName({
  previewFileName,
  selectedFileName,
  suppressDocumentLoadingOverlay = false,
  documentLoadState,
}: OverlayTargetFileNameInput): string | null {
  if (suppressDocumentLoadingOverlay) {
    return null;
  }

  if (documentLoadState.status !== 'idle' && documentLoadState.fileName) {
    return documentLoadState.fileName;
  }

  if (previewFileName) {
    return previewFileName;
  }

  return selectedFileName;
}

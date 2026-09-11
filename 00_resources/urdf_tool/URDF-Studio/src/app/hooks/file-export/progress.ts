import type { ExportProgressState } from '@/features/file-io';

const PROGRESS_MIN_UPDATE_INTERVAL_MS = 120;
const PROGRESS_MIN_DELTA = 0.02;

export type ExportProgressReporter = (
  currentStep: number,
  stepLabel: string,
  detail: string,
  options?: {
    stageProgress?: number;
    indeterminate?: boolean;
  },
) => void;

export function replaceTemplate(
  template: string,
  replacements: Record<string, string | number>,
): string {
  return Object.entries(replacements).reduce(
    (result, [key, value]) => result.replaceAll(`{${key}}`, String(value)),
    template,
  );
}

export function trimProgressFileLabel(filePath: string | null | undefined): string {
  const normalized = String(filePath || '')
    .trim()
    .replace(/\\/g, '/');
  if (!normalized) {
    return '';
  }

  const segments = normalized.split('/').filter(Boolean);
  if (segments.length <= 2) {
    return segments.join('/');
  }

  return segments.slice(-2).join('/');
}

export function createExportProgressReporter(
  onProgress: ((progress: ExportProgressState) => void) | undefined,
  totalSteps: number,
): ExportProgressReporter {
  let lastProgress: ExportProgressState | null = null;
  let lastReportedAt = 0;

  return (currentStep, stepLabel, detail, options = {}) => {
    if (!onProgress) {
      return;
    }

    const indeterminate = options.indeterminate ?? options.stageProgress == null;
    const fallbackStageProgress = indeterminate ? 0.24 : 0;
    const stageProgress = Math.min(1, Math.max(0, options.stageProgress ?? fallbackStageProgress));

    const nextProgress: ExportProgressState = {
      stepLabel,
      detail,
      progress: Math.min(1, Math.max(0, (currentStep - 1 + stageProgress) / totalSteps)),
      currentStep,
      totalSteps,
      indeterminate,
    };

    const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
    const isFirstUpdate = lastProgress == null;
    const isStepTransition = lastProgress?.currentStep !== nextProgress.currentStep;
    const didIndeterminateChange = lastProgress?.indeterminate !== nextProgress.indeterminate;
    const isTerminalUpdate = nextProgress.progress >= 0.999;
    const progressDelta = Math.abs((lastProgress?.progress ?? 0) - nextProgress.progress);
    const timeSinceLastReport = now - lastReportedAt;

    if (
      !isFirstUpdate &&
      !isStepTransition &&
      !didIndeterminateChange &&
      !isTerminalUpdate &&
      progressDelta < PROGRESS_MIN_DELTA &&
      timeSinceLastReport < PROGRESS_MIN_UPDATE_INTERVAL_MS
    ) {
      return;
    }

    lastProgress = nextProgress;
    lastReportedAt = now;
    onProgress(nextProgress);
  };
}

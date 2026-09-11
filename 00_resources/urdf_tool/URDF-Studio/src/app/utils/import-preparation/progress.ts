interface ImportPreparationProgressLike {
  progressPercent: number | null;
  processedEntries: number;
  totalEntries: number;
  processedBytes: number;
  totalBytes: number;
}

const LARGE_IMPORT_PROGRESS_ENTRY_THRESHOLD = 1000;
const LARGE_IMPORT_PROGRESS_ENTRY_BUCKET_SIZE = 100;
const LARGE_IMPORT_PROGRESS_BYTE_BUCKET_SIZE = 1024 * 1024;

function clampImportProgressPercent(value: number | null): number | null {
  if (!Number.isFinite(value ?? NaN)) {
    return null;
  }

  return Math.max(0, Math.min(100, Math.round(value ?? 0)));
}

export function createImportProgressEmitter<T extends ImportPreparationProgressLike>(
  onProgress?: (progress: T) => void,
): (progress: T) => void {
  let lastSignature: string | null = null;

  return (progress) => {
    if (!onProgress) {
      return;
    }

    const nextProgress = {
      ...progress,
      progressPercent: clampImportProgressPercent(progress.progressPercent),
      processedEntries: Math.max(0, Math.round(progress.processedEntries)),
      totalEntries: Math.max(0, Math.round(progress.totalEntries)),
      processedBytes: Math.max(0, Math.round(progress.processedBytes)),
      totalBytes: Math.max(0, Math.round(progress.totalBytes)),
    } as T;
    const isInitial = nextProgress.processedEntries === 0;
    const isComplete =
      nextProgress.totalEntries > 0 &&
      nextProgress.processedEntries >= nextProgress.totalEntries;
    const shouldBucketEntryProgress =
      nextProgress.totalEntries >= LARGE_IMPORT_PROGRESS_ENTRY_THRESHOLD &&
      !isInitial &&
      !isComplete;
    const signature = JSON.stringify({
      ...nextProgress,
      processedEntries: shouldBucketEntryProgress
        ? Math.floor(
            nextProgress.processedEntries / LARGE_IMPORT_PROGRESS_ENTRY_BUCKET_SIZE,
          )
        : nextProgress.processedEntries,
      processedBytes: shouldBucketEntryProgress
        ? Math.floor(nextProgress.processedBytes / LARGE_IMPORT_PROGRESS_BYTE_BUCKET_SIZE)
        : nextProgress.processedBytes,
    });
    if (signature === lastSignature) {
      return;
    }
    lastSignature = signature;
    onProgress(nextProgress);
  };
}

export function mapImportProgressToPercentRange<T extends ImportPreparationProgressLike>(
  progress: T,
  rangeStart: number,
  rangeEnd: number,
): T {
  if (progress.progressPercent == null) {
    return progress;
  }

  const clampedPercent = clampImportProgressPercent(progress.progressPercent) ?? 0;
  const progressRatio = clampedPercent / 100;

  return {
    ...progress,
    progressPercent: rangeStart + progressRatio * (rangeEnd - rangeStart),
  };
}

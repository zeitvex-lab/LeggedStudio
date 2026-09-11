import { logRuntimeFailure } from '@/core/utils/runtimeDiagnostics';

export interface ScheduleUsdResolvedRobotRepublishOptions {
  isActive: () => boolean;
  requestAnimationFrame: (callback: () => void) => unknown;
  startWarmups: () => Array<Promise<unknown> | null | undefined>;
  onSettled: () => void;
}

export function scheduleUsdResolvedRobotRepublishAfterWarmup({
  isActive,
  requestAnimationFrame,
  startWarmups,
  onSettled,
}: ScheduleUsdResolvedRobotRepublishOptions): void {
  requestAnimationFrame(() => {
    if (!isActive()) {
      return;
    }

    let warmupCandidates: Array<Promise<unknown> | null | undefined>;
    try {
      warmupCandidates = Array.from(startWarmups() || []);
    } catch (error) {
      logRuntimeFailure(
        'UsdResolvedRobotWarmup:startWarmups',
        new Error('Failed to start USD resolved robot warmups.', { cause: error }),
      );
      warmupCandidates = [Promise.reject(error)];
    }

    const warmups = warmupCandidates
      .filter((candidate): candidate is Promise<unknown> => Boolean(candidate))
      .map((candidate) => Promise.resolve(candidate));

    if (warmups.length === 0) {
      if (isActive()) {
        onSettled();
      }
      return;
    }

    void Promise.allSettled(warmups).then(() => {
      if (!isActive()) {
        return;
      }

      onSettled();
    });
  });
}

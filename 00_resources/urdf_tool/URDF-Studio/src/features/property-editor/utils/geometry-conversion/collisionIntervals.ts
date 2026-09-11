import type { ScalarInterval } from './conversionTypes';

export function subtractBlockedInterval(
  intervals: ScalarInterval[],
  blockedStart: number,
  blockedEnd: number,
): ScalarInterval[] {
  if (
    !Number.isFinite(blockedStart) ||
    !Number.isFinite(blockedEnd) ||
    blockedEnd <= blockedStart
  ) {
    return intervals;
  }

  const nextIntervals: ScalarInterval[] = [];

  intervals.forEach((interval) => {
    if (blockedEnd <= interval.start || blockedStart >= interval.end) {
      nextIntervals.push(interval);
      return;
    }

    if (blockedStart > interval.start) {
      nextIntervals.push({
        start: interval.start,
        end: Math.min(blockedStart, interval.end),
      });
    }

    if (blockedEnd < interval.end) {
      nextIntervals.push({
        start: Math.max(blockedEnd, interval.start),
        end: interval.end,
      });
    }
  });

  return nextIntervals.filter((interval) => interval.end - interval.start > 1e-8);
}

export function mergeIntervals(intervals: ScalarInterval[]): ScalarInterval[] {
  if (intervals.length === 0) return [];

  const sorted = [...intervals].sort(
    (left, right) => left.start - right.start || left.end - right.end,
  );
  const merged: ScalarInterval[] = [{ ...sorted[0] }];

  for (let index = 1; index < sorted.length; index += 1) {
    const current = sorted[index];
    const last = merged[merged.length - 1];

    if (current.start <= last.end + 1e-8) {
      last.end = Math.max(last.end, current.end);
      continue;
    }

    merged.push({ ...current });
  }

  return merged;
}

export function choosePreferredInterval(intervals: ScalarInterval[]): ScalarInterval | null {
  if (intervals.length === 0) return null;

  return intervals.reduce<ScalarInterval | null>((best, interval) => {
    if (!best) return interval;

    const intervalLength = interval.end - interval.start;
    const bestLength = best.end - best.start;
    if (intervalLength > bestLength + 1e-8) {
      return interval;
    }

    if (Math.abs(intervalLength - bestLength) <= 1e-8) {
      const intervalMidpoint = Math.abs((interval.start + interval.end) / 2);
      const bestMidpoint = Math.abs((best.start + best.end) / 2);
      if (intervalMidpoint < bestMidpoint - 1e-8) {
        return interval;
      }
    }

    return best;
  }, null);
}

export function resolveAvailableSweepIntervalFromBlockedIntervals(
  sweepHalfExtent: number,
  blockedIntervals: ScalarInterval[],
): { centerShift: number; sweepHalfExtent: number } | null {
  if (sweepHalfExtent <= 1e-8) {
    const blockingInterval = blockedIntervals.find(
      (interval) => interval.start <= 0 + 1e-8 && interval.end >= 0 - 1e-8,
    );

    return blockingInterval
      ? null
      : {
          centerShift: 0,
          sweepHalfExtent: 0,
        };
  }

  let intervals: ScalarInterval[] = [{ start: -sweepHalfExtent, end: sweepHalfExtent }];
  blockedIntervals.forEach((interval) => {
    intervals = subtractBlockedInterval(intervals, interval.start, interval.end);
  });

  const preferredInterval = choosePreferredInterval(intervals);
  if (!preferredInterval) {
    return null;
  }

  return {
    centerShift: (preferredInterval.start + preferredInterval.end) / 2,
    sweepHalfExtent: Math.max((preferredInterval.end - preferredInterval.start) / 2, 0),
  };
}

export function findNearestSafeCenterShiftFromBlockedIntervals(
  blockedIntervals: ScalarInterval[],
): number {
  const blockingInterval = blockedIntervals.find(
    (interval) => interval.start <= 0 + 1e-8 && interval.end >= 0 - 1e-8,
  );

  if (!blockingInterval) {
    return 0;
  }

  const leftMagnitude = Math.abs(blockingInterval.start);
  const rightMagnitude = Math.abs(blockingInterval.end);

  if (leftMagnitude < rightMagnitude - 1e-8) {
    return blockingInterval.start;
  }

  if (rightMagnitude < leftMagnitude - 1e-8) {
    return blockingInterval.end;
  }

  return blockingInterval.end;
}

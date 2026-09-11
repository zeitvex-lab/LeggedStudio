export function resolveUsdPreloadConcurrency(preferredConcurrency?: number): number {
  const fallbackConcurrency = Number(globalThis.navigator?.hardwareConcurrency || 4);
  const resolvedConcurrency = preferredConcurrency ?? fallbackConcurrency;
  return Math.max(2, Math.min(10, Math.floor(resolvedConcurrency) || 2));
}

export async function runWithConcurrency<T>(
  items: readonly T[],
  maxConcurrency: number,
  isActive: () => boolean,
  handler: (item: T, index: number) => Promise<void>,
): Promise<void> {
  if (!Array.isArray(items) || items.length === 0) {
    return;
  }

  const concurrency = Math.max(1, Math.min(Math.floor(maxConcurrency) || 1, items.length));
  let cursor = 0;

  const workers = Array.from({ length: concurrency }, async () => {
    while (cursor < items.length) {
      if (!isActive()) {
        return;
      }

      const currentIndex = cursor;
      cursor += 1;
      await handler(items[currentIndex]!, currentIndex);
    }
  });

  await Promise.all(workers);
}

export function splitUsdStagePreloadEntries<T extends { path: string }>(
  stageSourcePath: string,
  entries: readonly T[],
): {
  dependencyEntries: T[];
  rootEntry: T | null;
} {
  let rootEntry: T | null = null;
  const dependencyEntries: T[] = [];

  entries.forEach((entry) => {
    if (!rootEntry && entry.path === stageSourcePath) {
      rootEntry = entry;
      return;
    }
    dependencyEntries.push(entry);
  });

  return {
    dependencyEntries,
    rootEntry,
  };
}

export async function preloadUsdStageEntries<T extends { path: string }>(args: {
  stageSourcePath: string;
  entries: readonly T[];
  isActive: () => boolean;
  preloadEntry: (entry: T, isActive: () => boolean) => Promise<void>;
  concurrency?: number;
}): Promise<void> {
  const {
    stageSourcePath,
    entries,
    isActive,
    preloadEntry,
    concurrency,
  } = args;

  const {
    dependencyEntries,
    rootEntry,
  } = splitUsdStagePreloadEntries(stageSourcePath, entries);

  await runWithConcurrency(
    dependencyEntries,
    resolveUsdPreloadConcurrency(concurrency),
    isActive,
    async (entry) => {
      if (!isActive()) {
        return;
      }
      await preloadEntry(entry, isActive);
    },
  );

  if (!isActive() || !rootEntry) {
    return;
  }

  await preloadEntry(rootEntry, isActive);
}

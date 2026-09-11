import { translations } from '@/shared/i18n';
import { useAssetsStore, useUIStore } from '@/store';
import { createAssetUrls, revokeBlobUrls } from './import_blob_urls';
import { hydrateDeferredImportAssetsWithWorker } from './importPreparationWorkerBridge';

function stillOwnsExpectedImportedFiles(expectedFileNames: readonly string[]): boolean {
  if (expectedFileNames.length === 0) {
    return true;
  }

  const assetsState = useAssetsStore.getState();
  return expectedFileNames.some((fileName) =>
    assetsState.availableFiles.some((file) => file.name === fileName),
  );
}

function shouldIgnoreDeferredHydrationResult(options: {
  expectedFileNames?: readonly string[];
  isCurrentImport?: () => boolean;
}): boolean {
  return (
    options.isCurrentImport?.() === false ||
    !stillOwnsExpectedImportedFiles(options.expectedFileNames ?? [])
  );
}

export function hydrateDeferredArchiveAssetsInBackground(
  archiveFile: File,
  assetFiles: Parameters<typeof hydrateDeferredImportAssetsWithWorker>[0]['assetFiles'],
  options: {
    expectedFileNames?: readonly string[];
    isCurrentImport?: () => boolean;
    onShowToast?: (message: string, type?: 'info' | 'success') => void;
  },
): void {
  if (assetFiles.length === 0) {
    return;
  }

  void (async () => {
    try {
      const hydratedAssetFiles = await hydrateDeferredImportAssetsWithWorker({
        archiveFile,
        assetFiles,
      });
      if (hydratedAssetFiles.length === 0) {
        return;
      }

      const hydratedAssetUrls = await createAssetUrls(hydratedAssetFiles);
      if (shouldIgnoreDeferredHydrationResult(options)) {
        revokeBlobUrls(Object.values(hydratedAssetUrls));
        return;
      }

      useAssetsStore.getState().addAssets(hydratedAssetUrls);
    } catch (error) {
      if (shouldIgnoreDeferredHydrationResult(options)) {
        return;
      }

      console.error('Deferred archive asset hydration failed after import completed:', error);
      const message =
        translations[useUIStore.getState().lang].importBackgroundAssetsStillLoadingFailed;
      options.onShowToast?.(message, 'info');
    }
  })();
}

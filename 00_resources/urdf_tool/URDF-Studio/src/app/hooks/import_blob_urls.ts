import { waitForAnimationFrame } from '@/app/utils/waitForAnimationFrame';

export type BlobBackedAssetFile = {
  name: string;
  blob: Blob;
};

const ASSET_URL_CREATION_YIELD_INTERVAL = 256;

export function revokeBlobUrls(urls: readonly string[]): void {
  Array.from(new Set(urls)).forEach((url) => {
    if (url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
  });
}

export async function createAssetUrls(
  assetFiles: BlobBackedAssetFile[],
  options: {
    onProgress?: (progress: { processedEntries: number; totalEntries: number }) => void;
    yieldToBrowser?: boolean;
  } = {},
): Promise<Record<string, string>> {
  const assets: Record<string, string> = {};

  options.onProgress?.({ processedEntries: 0, totalEntries: assetFiles.length });

  for (let index = 0; index < assetFiles.length; index += 1) {
    const file = assetFiles[index];
    const normalizedPath = file.name.replace(/\\/g, '/').replace(/^\/+/, '');
    assets[normalizedPath] = URL.createObjectURL(file.blob);

    if (
      options.yieldToBrowser &&
      (index + 1) % ASSET_URL_CREATION_YIELD_INTERVAL === 0
    ) {
      await waitForAnimationFrame();
    }

    if (
      options.onProgress &&
      ((index + 1) % ASSET_URL_CREATION_YIELD_INTERVAL === 0 ||
        index + 1 === assetFiles.length)
    ) {
      options.onProgress({
        processedEntries: index + 1,
        totalEntries: assetFiles.length,
      });
    }
  }

  return assets;
}

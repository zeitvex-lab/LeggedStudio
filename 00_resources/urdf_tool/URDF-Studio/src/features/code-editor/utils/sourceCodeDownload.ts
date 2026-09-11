import type { SourceCodeDocumentFlavor } from '../types';

export interface DownloadSourceCodeDocumentOptions {
  content: string;
  fileName: string;
  documentFlavor: SourceCodeDocumentFlavor;
  onDownload?: () => void;
}

export const getDownloadFileName = (
  fileName: string,
  documentFlavor: SourceCodeDocumentFlavor,
): string => {
  if (documentFlavor !== 'equivalent-mjcf') {
    return fileName;
  }

  const strippedName = fileName.replace(/\.(usd|usda|usdc|usdz)$/i, '');
  return `${strippedName}.equivalent.mjcf`;
};

export const downloadSourceCodeDocument = ({
  content,
  fileName,
  documentFlavor,
  onDownload,
}: DownloadSourceCodeDocumentOptions): boolean => {
  if (documentFlavor === 'equivalent-mjcf') {
    return false;
  }

  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = getDownloadFileName(fileName, documentFlavor);
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
  onDownload?.();
  return true;
};

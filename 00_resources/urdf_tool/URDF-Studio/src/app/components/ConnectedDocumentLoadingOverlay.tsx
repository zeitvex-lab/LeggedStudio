import type { Language } from '@/shared/i18n';
import { useAssetsStore } from '@/store';
import { DocumentLoadingOverlay } from './DocumentLoadingOverlay';

interface ConnectedDocumentLoadingOverlayProps {
  lang: Language;
  targetFileName: string | null;
}

export function ConnectedDocumentLoadingOverlay({
  lang,
  targetFileName,
}: ConnectedDocumentLoadingOverlayProps) {
  const documentLoadState = useAssetsStore((state) => state.documentLoadState);

  if (!targetFileName || documentLoadState.fileName !== targetFileName) {
    return null;
  }

  return <DocumentLoadingOverlay state={documentLoadState} lang={lang} />;
}

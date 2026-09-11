import { useMemo } from 'react';

import { markUnsavedChangesBaselineSaved } from '../utils/unsavedChangesBaseline';
import type { SourceCodeEditorDocument } from '@/features/code-editor';
import type { SourceCodeEditorApplyRequest } from '@/features/code-editor';
import type {
  SourceCodeDocumentChangeTarget,
  SourceCodeDocumentDescriptor,
} from '@/app/utils/sourceCodeDocuments';

type HandleCodeChange = (
  newCode: string,
  target?: SourceCodeDocumentChangeTarget,
  applyRequest?: SourceCodeEditorApplyRequest,
) => Promise<boolean>;

export function useSourceCodeEditorDocuments(
  sourceCodeDocuments: SourceCodeDocumentDescriptor[],
  handleCodeChange: HandleCodeChange,
): SourceCodeEditorDocument[] {
  return useMemo(
    () =>
      sourceCodeDocuments.map((document) => ({
        id: document.id,
        code: document.content,
        fileName: document.fileName,
        tabLabel: document.tabLabel,
        filePath: document.filePath ?? undefined,
        contentUrl: document.contentUrl,
        documentFlavor: document.documentFlavor,
        readOnly: document.readOnly,
        validationEnabled: document.validationEnabled,
        onCodeChange: (newCode: string, applyRequest?: SourceCodeEditorApplyRequest) =>
          handleCodeChange(newCode, document.changeTarget, applyRequest),
        onDownload: document.readOnly
          ? undefined
          : () => {
              markUnsavedChangesBaselineSaved();
            },
      })),
    [handleCodeChange, sourceCodeDocuments],
  );
}

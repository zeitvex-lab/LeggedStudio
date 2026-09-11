import { useEffect } from 'react';

import { getSourceCodeAutoApplyDebounceMs } from '../utils/editorPerformance';

export interface UseSourceCodeEditorAutoApplyOptions {
  enabled?: boolean;
  currentCode: string;
  isDirty: boolean;
  isReadOnly: boolean;
  supportsValidation: boolean;
  validationErrorCount: number;
  isValidationPending: boolean;
  isApplying: boolean;
  autoApplyBlockedCode?: string | null;
  onAutoApply: () => void;
  resolveDebounceMs?: (codeLength: number) => number;
}

export function useSourceCodeEditorAutoApply({
  enabled = true,
  currentCode,
  isDirty,
  isReadOnly,
  supportsValidation,
  validationErrorCount,
  isValidationPending,
  isApplying,
  autoApplyBlockedCode = null,
  onAutoApply,
  resolveDebounceMs = getSourceCodeAutoApplyDebounceMs,
}: UseSourceCodeEditorAutoApplyOptions) {
  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    if (!isDirty || isReadOnly || isApplying) {
      return undefined;
    }

    if (autoApplyBlockedCode === currentCode) {
      return undefined;
    }

    if (supportsValidation && (isValidationPending || validationErrorCount > 0)) {
      return undefined;
    }

    const timeoutId = globalThis.setTimeout(() => {
      onAutoApply();
    }, resolveDebounceMs(currentCode.length));

    return () => {
      globalThis.clearTimeout(timeoutId);
    };
  }, [
    autoApplyBlockedCode,
    currentCode,
    enabled,
    isApplying,
    isDirty,
    isReadOnly,
    isValidationPending,
    onAutoApply,
    resolveDebounceMs,
    supportsValidation,
    validationErrorCount,
  ]);
}

let regressionBeforeUnloadPromptSuppressed = false;
const regressionBeforeUnloadPromptListeners = new Set<(suppressed: boolean) => void>();

export function isRegressionBeforeUnloadPromptSuppressed(): boolean {
  return regressionBeforeUnloadPromptSuppressed;
}

export function subscribeRegressionBeforeUnloadPromptSuppression(
  listener: (suppressed: boolean) => void,
): () => void {
  regressionBeforeUnloadPromptListeners.add(listener);
  return () => {
    regressionBeforeUnloadPromptListeners.delete(listener);
  };
}

export function setRegressionBeforeUnloadPromptSuppressed(suppressed: boolean): void {
  if (regressionBeforeUnloadPromptSuppressed === suppressed) {
    return;
  }

  regressionBeforeUnloadPromptSuppressed = suppressed;
  regressionBeforeUnloadPromptListeners.forEach((listener) => {
    listener(suppressed);
  });
}

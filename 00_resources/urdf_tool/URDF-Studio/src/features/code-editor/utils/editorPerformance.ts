export const getUrdfValidationDebounceMs = (codeLength: number): number => {
  if (codeLength <= 2_000) {
    return 120;
  }

  if (codeLength <= 15_000) {
    return 180;
  }

  return 320;
};

export const getSourceCodeAutoApplyDebounceMs = (codeLength: number): number => {
  if (codeLength <= 2_000) {
    return 500;
  }

  if (codeLength <= 15_000) {
    return 700;
  }

  return 900;
};

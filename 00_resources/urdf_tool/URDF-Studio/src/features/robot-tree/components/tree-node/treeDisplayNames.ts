export function stripTreeDisplayNamePrefix(value: string, prefix?: string): string {
  const trimmedValue = value.trim();
  const trimmedPrefix = prefix?.trim();
  if (!trimmedPrefix) return trimmedValue;

  const separators = ['_', '-', ' ', ':'];
  const matchingSeparator = separators.find((separator) =>
    trimmedValue.startsWith(`${trimmedPrefix}${separator}`),
  );
  return matchingSeparator
    ? trimmedValue.slice(trimmedPrefix.length + matchingSeparator.length)
    : trimmedValue;
}

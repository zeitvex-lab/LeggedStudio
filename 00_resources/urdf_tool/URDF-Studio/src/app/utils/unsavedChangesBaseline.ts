type UnsavedChangesBaselineMarker = (() => void) | null;

let unsavedChangesBaselineMarker: UnsavedChangesBaselineMarker = null;

export function registerUnsavedChangesBaselineMarker(
  marker: UnsavedChangesBaselineMarker,
): void {
  unsavedChangesBaselineMarker = marker;
}

export function markUnsavedChangesBaselineSaved(): void {
  unsavedChangesBaselineMarker?.();
}

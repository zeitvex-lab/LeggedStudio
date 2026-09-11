export type BridgePickTarget = 'parent' | 'child';

export interface BridgePickAssignmentInput {
  selectedComponentId: string | null | undefined;
  parentComponentId: string | null | undefined;
  childComponentId: string | null | undefined;
  preferredTarget?: BridgePickTarget | null;
}

function normalizeId(value: string | null | undefined): string | null {
  return value || null;
}

function canAssignSide(
  side: BridgePickTarget,
  selectedComponentId: string,
  parentComponentId: string | null,
  childComponentId: string | null,
): boolean {
  const oppositeComponentId = side === 'parent' ? childComponentId : parentComponentId;
  return !oppositeComponentId || selectedComponentId !== oppositeComponentId;
}

export function resolveBridgePickAssignment({
  selectedComponentId,
  parentComponentId,
  childComponentId,
  preferredTarget,
}: BridgePickAssignmentInput): BridgePickTarget | null {
  const selected = normalizeId(selectedComponentId);
  const parent = normalizeId(parentComponentId);
  const child = normalizeId(childComponentId);

  if (!selected) {
    return null;
  }

  if (parent === selected && canAssignSide('parent', selected, parent, child)) {
    return 'parent';
  }

  if (child === selected && canAssignSide('child', selected, parent, child)) {
    return 'child';
  }

  if (!parent && canAssignSide('parent', selected, parent, child)) {
    return 'parent';
  }

  if (!child && canAssignSide('child', selected, parent, child)) {
    return 'child';
  }

  if (
    preferredTarget &&
    canAssignSide(preferredTarget, selected, parent, child)
  ) {
    return preferredTarget;
  }

  return null;
}

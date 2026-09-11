export interface UsdCollisionMeshAssignmentItem {
  meshId: string;
  authoredOrder: number;
}

interface ReconcileUsdCollisionMeshAssignmentsOptions {
  meshes: UsdCollisionMeshAssignmentItem[];
  currentCount: number;
  previousAssignments?: Map<string, number>;
  deletedObjectIndex?: number | null;
}

function sortMeshesByAuthoredOrder(meshes: UsdCollisionMeshAssignmentItem[]): UsdCollisionMeshAssignmentItem[] {
  return [...meshes].sort((left, right) => {
    if (left.authoredOrder !== right.authoredOrder) {
      return left.authoredOrder - right.authoredOrder;
    }
    return left.meshId.localeCompare(right.meshId);
  });
}

export function reconcileUsdCollisionMeshAssignments({
  meshes,
  currentCount,
  previousAssignments,
  deletedObjectIndex = null,
}: ReconcileUsdCollisionMeshAssignmentsOptions): Map<string, number | undefined> {
  const nextAssignments = new Map<string, number | undefined>();
  const sortedMeshes = sortMeshesByAuthoredOrder(meshes);
  const normalizedCurrentCount = Math.max(0, Math.floor(currentCount));

  sortedMeshes.forEach(({ meshId }) => {
    nextAssignments.set(meshId, undefined);
  });

  const workingAssignments = new Map<string, number>();
  sortedMeshes.forEach(({ meshId }) => {
    const previousIndex = previousAssignments?.get(meshId);
    if (Number.isInteger(previousIndex)) {
      workingAssignments.set(meshId, previousIndex as number);
    }
  });

  if (typeof deletedObjectIndex === 'number' && Number.isInteger(deletedObjectIndex)) {
    for (const [meshId, assignedIndex] of workingAssignments.entries()) {
      if (assignedIndex === deletedObjectIndex) {
        workingAssignments.delete(meshId);
        continue;
      }

      if (assignedIndex > deletedObjectIndex) {
        workingAssignments.set(meshId, assignedIndex - 1);
      }
    }
  }

  for (const [meshId, assignedIndex] of workingAssignments.entries()) {
    if (assignedIndex < 0 || assignedIndex >= normalizedCurrentCount) {
      workingAssignments.delete(meshId);
    }
  }

  const uniqueAssignments = new Map<string, number>();
  const seenIndices = new Set<number>();
  sortedMeshes.forEach(({ meshId }) => {
    const assignedIndex = workingAssignments.get(meshId);
    if (
      typeof assignedIndex !== 'number' ||
      !Number.isInteger(assignedIndex) ||
      seenIndices.has(assignedIndex)
    ) {
      return;
    }

    uniqueAssignments.set(meshId, assignedIndex);
    seenIndices.add(assignedIndex);
  });

  const availableIndices: number[] = [];
  for (let index = 0; index < normalizedCurrentCount; index += 1) {
    if (!seenIndices.has(index)) {
      availableIndices.push(index);
    }
  }

  sortedMeshes.forEach(({ meshId }) => {
    if (uniqueAssignments.has(meshId)) {
      return;
    }

    const nextIndex = availableIndices.shift();
    if (nextIndex === undefined) {
      return;
    }

    uniqueAssignments.set(meshId, nextIndex);
  });

  sortedMeshes.forEach(({ meshId }) => {
    nextAssignments.set(meshId, uniqueAssignments.get(meshId));
  });

  return nextAssignments;
}

import type { UsdSceneSnapshot } from '@/types';

const SNAPSHOT_BUFFER_KEYS = ['positions', 'indices', 'normals', 'uvs', 'transforms'] as const;

function hasArrayLikeValues(value: unknown): boolean {
  if (!value) {
    return false;
  }

  if (ArrayBuffer.isView(value)) {
    return value.byteLength > 0;
  }

  if (Array.isArray(value)) {
    return value.length > 0;
  }

  if (typeof value === 'object' && typeof (value as ArrayLike<number>).length === 'number') {
    return Number((value as ArrayLike<number>).length) > 0;
  }

  return false;
}

export function hasUsdSceneSnapshotHeavyBuffers(
  snapshot: UsdSceneSnapshot | null | undefined,
): boolean {
  const buffers = snapshot?.buffers;
  if (!buffers || typeof buffers !== 'object') {
    return false;
  }

  return SNAPSHOT_BUFFER_KEYS.some((key) => hasArrayLikeValues(buffers[key]));
}

export function stripTransferHeavyUsdSceneSnapshotBuffers(
  snapshot: UsdSceneSnapshot | null | undefined,
): UsdSceneSnapshot | null {
  if (!snapshot || typeof snapshot !== 'object') {
    return null;
  }

  if (!hasUsdSceneSnapshotHeavyBuffers(snapshot)) {
    return snapshot;
  }

  return {
    ...snapshot,
    buffers: snapshot.buffers?.rangesByMeshId
      ? {
          rangesByMeshId: snapshot.buffers.rangesByMeshId,
        }
      : null,
  };
}

export function collectUsdSceneSnapshotTransferables(
  snapshot: UsdSceneSnapshot | null | undefined,
): ArrayBuffer[] {
  const buffers = snapshot?.buffers;
  if (!buffers || typeof buffers !== 'object') {
    return [];
  }

  const transferables: ArrayBuffer[] = [];
  const seen = new Set<ArrayBuffer>();

  SNAPSHOT_BUFFER_KEYS.forEach((key) => {
    const value = buffers[key];
    if (
      !ArrayBuffer.isView(value) ||
      !(value.buffer instanceof ArrayBuffer) ||
      value.byteLength <= 0
    ) {
      return;
    }

    if (seen.has(value.buffer)) {
      return;
    }

    seen.add(value.buffer);
    transferables.push(value.buffer);
  });

  return transferables;
}

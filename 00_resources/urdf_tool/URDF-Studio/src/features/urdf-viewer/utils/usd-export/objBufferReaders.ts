import { normalizeUsdPath } from './usdExportPaths.ts';

import type {
  MeshDescriptorRanges,
  MeshRange,
  SnapshotBuffers,
  SnapshotGeomSubsetSection,
  SnapshotMeshDescriptor,
} from './internalTypes.ts';

export function getDescriptorGeomSubsetSections(
  descriptor: SnapshotMeshDescriptor,
): SnapshotGeomSubsetSection[] {
  const geometry =
    descriptor.geometry && typeof descriptor.geometry === 'object'
      ? (descriptor.geometry as {
          geomSubsetSections?: Array<{
            start?: unknown;
            length?: unknown;
            materialId?: unknown;
          }> | null;
        })
      : null;
  const rawSections = Array.isArray(geometry?.geomSubsetSections)
    ? geometry.geomSubsetSections
    : [];

  return rawSections
    .map((section) => {
      const start = Number(section?.start);
      const length = Number(section?.length);
      if (!Number.isFinite(start) || !Number.isFinite(length) || length <= 0) {
        return null;
      }

      return {
        start: Math.max(0, Math.floor(start)),
        length: Math.max(0, Math.floor(length)),
        materialId: normalizeUsdPath(String(section?.materialId || '')) || null,
      } satisfies SnapshotGeomSubsetSection;
    })
    .filter(Boolean) as SnapshotGeomSubsetSection[];
}

export function getDescriptorRanges(
  descriptor: SnapshotMeshDescriptor,
  buffers: SnapshotBuffers | null | undefined,
): MeshDescriptorRanges | null {
  if (descriptor.ranges) {
    return descriptor.ranges;
  }

  const meshId = normalizeUsdPath(descriptor.meshId || '');
  if (!meshId) return null;
  return buffers?.rangesByMeshId?.[meshId] || null;
}

type NumericSubarrayLike = ArrayLike<number> & {
  subarray: (start: number, end: number) => ArrayLike<number>;
};

function hasNumericSubarray(value: ArrayLike<number>): value is NumericSubarrayLike {
  return (
    ArrayBuffer.isView(value) &&
    typeof (value as unknown as { subarray?: unknown }).subarray === 'function'
  );
}

export function readRangeValues(
  source: ArrayLike<number> | null | undefined,
  range: MeshRange | null | undefined,
): ArrayLike<number> {
  if (!source || !range) return [];
  const offset = Math.max(0, Number(range.offset || 0));
  const count = Math.max(0, Number(range.count || 0));
  if (count <= 0) return [];
  const sourceLength = Math.max(0, Number(source.length || 0));
  const end = offset + count;
  if (end <= sourceLength && hasNumericSubarray(source)) {
    return source.subarray(offset, end);
  }
  if (end <= sourceLength && Array.isArray(source)) {
    return source.slice(offset, end);
  }
  return Array.from({ length: count }, (_, index) => Number(source[offset + index] || 0));
}

export function readRangeNumber(values: ArrayLike<number>, index: number): number {
  return Number(values[index] || 0);
}

export function sliceRangeValues(
  values: ArrayLike<number>,
  start: number,
  end: number,
): ArrayLike<number> {
  const boundedStart = Math.max(0, Math.min(values.length, start));
  const boundedEnd = Math.max(boundedStart, Math.min(values.length, end));
  if (boundedStart === 0 && boundedEnd === values.length) {
    return values;
  }
  if (hasNumericSubarray(values)) {
    return values.subarray(boundedStart, boundedEnd);
  }
  if (Array.isArray(values)) {
    return values.slice(boundedStart, boundedEnd);
  }
  return Array.from({ length: boundedEnd - boundedStart }, (_, index) =>
    readRangeNumber(values, boundedStart + index),
  );
}

export function hasSnapshotBufferValues(value: ArrayLike<number> | null | undefined): boolean {
  if (!value) {
    return false;
  }

  if (ArrayBuffer.isView(value)) {
    return value.byteLength > 0;
  }

  if (Array.isArray(value)) {
    return value.length > 0;
  }

  return typeof value.length === 'number' && Number(value.length) > 0;
}

function getMeshDescriptorNormalDiagnostics(
  descriptor: SnapshotMeshDescriptor,
): SnapshotMeshDescriptor['normalDiagnostics'] {
  return descriptor.normalDiagnostics || descriptor.geometry?.normalDiagnostics || null;
}

export function hasTrustedSnapshotNormals(descriptor: SnapshotMeshDescriptor): boolean {
  const diagnostics = getMeshDescriptorNormalDiagnostics(descriptor);
  if (!diagnostics || typeof diagnostics !== 'object') {
    return false;
  }

  const postRepairLowDotCount = Number(diagnostics.postRepairLowDotCount);
  return Number.isFinite(postRepairLowDotCount) && postRepairLowDotCount === 0;
}

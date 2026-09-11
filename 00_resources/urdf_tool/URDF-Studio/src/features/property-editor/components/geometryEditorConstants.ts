import { GeometryType } from '@/types';
import { MAX_GEOMETRY_DIMENSION_DECIMALS } from '@/core/utils/numberPrecision';
import type { GeometryEditorTranslations } from './GeometryEditor.types';

export const GEOMETRY_EDITOR_COMPACT_ACTIONS_WIDTH = 360;
export const GEOMETRY_EDITOR_RELAXED_OVERLAP_ALLOWANCE_RATIO = 0.12;
export const GEOMETRY_EDITOR_RELAXED_FIT_VOLUME_WINDOW_RATIO = 1.75;
export const EDITABLE_GEOMETRY_TYPES: GeometryType[] = [
  GeometryType.BOX,
  GeometryType.CYLINDER,
  GeometryType.SPHERE,
  GeometryType.ELLIPSOID,
  GeometryType.CAPSULE,
  GeometryType.MESH,
];
export const MJCF_SPECIAL_GEOMETRY_TYPES = new Set<GeometryType>([
  GeometryType.PLANE,
  GeometryType.HFIELD,
  GeometryType.SDF,
]);
export const COLLISION_VISUAL_MESH_REFERENCE_TYPES = new Set<GeometryType>([
  GeometryType.BOX,
  GeometryType.CYLINDER,
  GeometryType.ELLIPSOID,
  GeometryType.CAPSULE,
]);
export const POSITIVE_GEOMETRY_VALUE_MIN = 10 ** -MAX_GEOMETRY_DIMENSION_DECIMALS;
export const MATERIAL_OPACITY_STEP = 0.05;
export const MATERIAL_OPACITY_DECIMALS = 3;

export const stripAxisSuffix = (label: string) => label.replace(/\s*\([^)]*\)\s*$/, '');

export function getGeometryTypeLabel(
  typeOption: GeometryType,
  t: GeometryEditorTranslations,
): string {
  if (typeOption === GeometryType.BOX) {
    return t.box;
  }

  if (typeOption === GeometryType.PLANE) {
    return t.plane;
  }

  if (typeOption === GeometryType.CYLINDER) {
    return t.cylinder;
  }

  if (typeOption === GeometryType.SPHERE) {
    return t.sphere;
  }

  if (typeOption === GeometryType.ELLIPSOID) {
    return t.ellipsoid;
  }

  if (typeOption === GeometryType.CAPSULE) {
    return t.capsule;
  }

  if (typeOption === GeometryType.HFIELD) {
    return t.hfield;
  }

  if (typeOption === GeometryType.SDF) {
    return t.sdf;
  }

  if (typeOption === GeometryType.MESH) {
    return t.mesh;
  }

  return t.none;
}

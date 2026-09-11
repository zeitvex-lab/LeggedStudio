import * as THREE from 'three';
import { GeometryType } from '@/types';

import { MathUtils } from './math.ts';

type GeometryTypeValue = 'box' | 'cylinder' | 'sphere' | 'capsule' | 'mesh' | 'none' | GeometryType;

interface Vector3Like {
  x?: number;
  y?: number;
  z?: number;
}

interface GeometryLike {
  type?: GeometryTypeValue;
  dimensions?: Vector3Like;
}

interface InertiaLike {
  ixx?: number;
  ixy?: number;
  ixz?: number;
  iyy?: number;
  iyz?: number;
  izz?: number;
}

interface InertialLike {
  mass?: number;
  inertia?: InertiaLike;
}

interface LinkLike {
  visual?: GeometryLike;
  collision?: GeometryLike;
  collisionBodies?: GeometryLike[];
  inertial?: InertialLike;
}

export interface PrincipalAxisVector {
  x: number;
  y: number;
  z: number;
}

export interface InertialDerivedValues {
  diagonalInertia: [number, number, number];
  principalAxes: [PrincipalAxisVector, PrincipalAxisVector, PrincipalAxisVector];
}

export interface InertiaTensorComponents {
  ixx: number;
  ixy: number;
  ixz: number;
  iyy: number;
  iyz: number;
  izz: number;
}

export interface MassScaledInertiaEstimate {
  inertia: InertiaTensorComponents;
  scale: number;
}

export interface LinkDensityResult {
  value: number | null;
  volume: number | null;
  source: 'collision' | 'visual' | null;
}

const MIN_VOLUME = 1e-8;

function toFiniteDimension(value: number | undefined, fallback = 0): number {
  return Number.isFinite(value) ? Number(value) : fallback;
}

function computeCapsuleVolume(totalLength: number, radius: number): number {
  if (totalLength <= 0 || radius <= 0) return 0;
  const clampedRadius = Math.min(radius, totalLength / 2);
  return (
    Math.PI * clampedRadius * clampedRadius * totalLength -
    (2 / 3) * Math.PI * clampedRadius * clampedRadius * clampedRadius
  );
}

function normalizeAxis(axis: PrincipalAxisVector): PrincipalAxisVector {
  const length = Math.hypot(axis.x, axis.y, axis.z);
  if (length <= 1e-12) {
    return { x: 1, y: 0, z: 0 };
  }

  let normalized = {
    x: axis.x / length,
    y: axis.y / length,
    z: axis.z / length,
  };

  const rankedComponents = [
    { key: 'x' as const, value: Math.abs(normalized.x) },
    { key: 'y' as const, value: Math.abs(normalized.y) },
    { key: 'z' as const, value: Math.abs(normalized.z) },
  ].sort((left, right) => right.value - left.value);

  const dominantKey = rankedComponents[0]?.key;
  const dominantValue = dominantKey ? normalized[dominantKey] : 1;

  if (dominantValue < 0) {
    normalized = {
      x: -normalized.x,
      y: -normalized.y,
      z: -normalized.z,
    };
  }

  return normalized;
}

function normalizeAxisOrFallback(
  axis: PrincipalAxisVector | undefined,
  fallback: PrincipalAxisVector,
): PrincipalAxisVector {
  const candidate = axis ?? fallback;
  const length = Math.hypot(candidate.x, candidate.y, candidate.z);
  if (length <= 1e-12) {
    return fallback;
  }

  return normalizeAxis(candidate);
}

function toFiniteMoment(value: number | undefined): number {
  return Number.isFinite(value) ? Number(value) : 0;
}

function sanitizeTensorComponent(value: number): number {
  return Math.abs(value) < 1e-12 ? 0 : value;
}

function hasFiniteInertiaTensor(
  inertia: InertiaLike | undefined,
): inertia is Required<InertiaLike> {
  if (!inertia) {
    return false;
  }

  return (
    Number.isFinite(Number(inertia.ixx)) &&
    Number.isFinite(Number(inertia.ixy)) &&
    Number.isFinite(Number(inertia.ixz)) &&
    Number.isFinite(Number(inertia.iyy)) &&
    Number.isFinite(Number(inertia.iyz)) &&
    Number.isFinite(Number(inertia.izz))
  );
}

export function computeGeometryVolume(geometry: GeometryLike | undefined): number | null {
  if (!geometry?.type || geometry.type === 'none' || geometry.type === 'mesh') {
    return null;
  }

  const x = Math.max(toFiniteDimension(geometry.dimensions?.x), 0);
  const y = Math.max(toFiniteDimension(geometry.dimensions?.y), 0);
  const z = Math.max(toFiniteDimension(geometry.dimensions?.z, x), 0);

  if (geometry.type === 'box') {
    return Math.max(x * y * z, 0);
  }

  if (geometry.type === 'cylinder') {
    return Math.PI * x * x * y;
  }

  if (geometry.type === 'sphere') {
    return (4 / 3) * Math.PI * x * Math.max(y, x) * Math.max(z, x);
  }

  if (geometry.type === 'capsule') {
    return computeCapsuleVolume(y, x);
  }

  return null;
}

function computeDensityFromGeometries(
  mass: number,
  geometries: GeometryLike[],
): { value: number | null; volume: number | null } {
  const volumes = geometries.map((geometry) => computeGeometryVolume(geometry));
  if (volumes.some((volume) => volume === null)) {
    return { value: null, volume: null };
  }

  const numericVolumes = volumes.filter((volume): volume is number => volume !== null);
  const totalVolume = numericVolumes.reduce((sum, volume) => sum + volume, 0);
  if (!Number.isFinite(totalVolume) || totalVolume < MIN_VOLUME || mass <= 0) {
    return { value: null, volume: totalVolume || null };
  }

  return {
    value: mass / totalVolume,
    volume: totalVolume,
  };
}

export function computeLinkDensity(link: LinkLike | undefined): LinkDensityResult {
  const mass = Number(link?.inertial?.mass ?? 0);
  const collisionGeometries = [link?.collision, ...(link?.collisionBodies ?? [])].filter(
    (geometry): geometry is GeometryLike => Boolean(geometry?.type && geometry.type !== 'none'),
  );

  if (collisionGeometries.length > 0) {
    const density = computeDensityFromGeometries(mass, collisionGeometries);
    return {
      ...density,
      source: 'collision',
    };
  }

  if (link?.visual?.type && link.visual.type !== 'none') {
    const density = computeDensityFromGeometries(mass, [link.visual]);
    return {
      ...density,
      source: 'visual',
    };
  }

  return {
    value: null,
    volume: null,
    source: null,
  };
}

export function computeInertialDerivedValues(
  inertial: InertialLike | undefined,
): InertialDerivedValues | null {
  if (!inertial?.inertia) {
    return null;
  }

  const matrix = new THREE.Matrix3();
  matrix.set(
    Number(inertial.inertia.ixx ?? 0),
    Number(inertial.inertia.ixy ?? 0),
    Number(inertial.inertia.ixz ?? 0),
    Number(inertial.inertia.ixy ?? 0),
    Number(inertial.inertia.iyy ?? 0),
    Number(inertial.inertia.iyz ?? 0),
    Number(inertial.inertia.ixz ?? 0),
    Number(inertial.inertia.iyz ?? 0),
    Number(inertial.inertia.izz ?? 0),
  );

  const decomposition = MathUtils.computeEigenDecomposition3x3(matrix);
  const principalPairs = decomposition.eigenvalues
    .map((value, index) => ({
      value,
      axis: normalizeAxis({
        x: decomposition.eigenvectors[index][0],
        y: decomposition.eigenvectors[index][1],
        z: decomposition.eigenvectors[index][2],
      }),
    }))
    .sort((left, right) => left.value - right.value);

  if (principalPairs.some((entry) => !Number.isFinite(entry.value))) {
    return null;
  }

  return {
    diagonalInertia: [principalPairs[0].value, principalPairs[1].value, principalPairs[2].value],
    principalAxes: [principalPairs[0].axis, principalPairs[1].axis, principalPairs[2].axis],
  };
}

export function composeInertiaTensorFromDerivedValues(
  diagonalInertia: [number, number, number],
  principalAxes: [PrincipalAxisVector, PrincipalAxisVector, PrincipalAxisVector],
): InertiaTensorComponents {
  const axes = [
    normalizeAxisOrFallback(principalAxes[0], { x: 1, y: 0, z: 0 }),
    normalizeAxisOrFallback(principalAxes[1], { x: 0, y: 1, z: 0 }),
    normalizeAxisOrFallback(principalAxes[2], { x: 0, y: 0, z: 1 }),
  ] as const;

  const moments = [
    toFiniteMoment(diagonalInertia[0]),
    toFiniteMoment(diagonalInertia[1]),
    toFiniteMoment(diagonalInertia[2]),
  ] as const;

  const sumMomentProducts = (
    rowAccessor: (axis: PrincipalAxisVector) => number,
    colAccessor: (axis: PrincipalAxisVector) => number,
  ): number =>
    moments.reduce(
      (sum, moment, index) => sum + moment * rowAccessor(axes[index]!) * colAccessor(axes[index]!),
      0,
    );

  return {
    ixx: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.x,
        (axis) => axis.x,
      ),
    ),
    ixy: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.x,
        (axis) => axis.y,
      ),
    ),
    ixz: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.x,
        (axis) => axis.z,
      ),
    ),
    iyy: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.y,
        (axis) => axis.y,
      ),
    ),
    iyz: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.y,
        (axis) => axis.z,
      ),
    ),
    izz: sanitizeTensorComponent(
      sumMomentProducts(
        (axis) => axis.z,
        (axis) => axis.z,
      ),
    ),
  };
}

export function scaleInertiaTensorForMassChange(
  inertial: InertialLike | undefined,
  nextMass: number,
): MassScaledInertiaEstimate | null {
  const currentMass = Number(inertial?.mass ?? 0);
  if (!Number.isFinite(nextMass) || nextMass < 0 || currentMass <= 0) {
    return null;
  }

  if (!hasFiniteInertiaTensor(inertial?.inertia)) {
    return null;
  }

  const scale = nextMass / currentMass;

  return {
    scale,
    inertia: {
      ixx: sanitizeTensorComponent(Number(inertial.inertia.ixx) * scale),
      ixy: sanitizeTensorComponent(Number(inertial.inertia.ixy) * scale),
      ixz: sanitizeTensorComponent(Number(inertial.inertia.ixz) * scale),
      iyy: sanitizeTensorComponent(Number(inertial.inertia.iyy) * scale),
      iyz: sanitizeTensorComponent(Number(inertial.inertia.iyz) * scale),
      izz: sanitizeTensorComponent(Number(inertial.inertia.izz) * scale),
    },
  };
}

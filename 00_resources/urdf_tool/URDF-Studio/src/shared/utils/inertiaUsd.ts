import * as THREE from 'three';

import { MathUtils } from './math.ts';

interface Vector3Like {
  x?: number;
  y?: number;
  z?: number;
}

interface EulerLike {
  r?: number;
  p?: number;
  y?: number;
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
  origin?: {
    xyz?: Vector3Like;
    rpy?: EulerLike;
  };
  inertia?: InertiaLike;
}

export interface UsdInertiaProperties {
  diagonalInertia: [number, number, number];
  principalAxesLocal: THREE.Quaternion;
}

function sanitizeMoment(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Object.is(value, -0) ? 0 : value;
}

function createOriginQuaternion(inertial: InertialLike | undefined): THREE.Quaternion {
  return new THREE.Quaternion().setFromEuler(
    new THREE.Euler(
      inertial?.origin?.rpy?.r ?? 0,
      inertial?.origin?.rpy?.p ?? 0,
      inertial?.origin?.rpy?.y ?? 0,
      'ZYX',
    ),
  );
}

function buildPrincipalAxes(
  eigenvalues: number[],
  eigenvectors: number[][],
): { diagonalInertia: [number, number, number]; principalAxes: THREE.Quaternion } {
  const pairs = eigenvalues.map((value, index) => ({
    value: sanitizeMoment(value),
    vector: new THREE.Vector3(
      eigenvectors[0]?.[index] ?? 0,
      eigenvectors[1]?.[index] ?? 0,
      eigenvectors[2]?.[index] ?? 0,
    ).normalize(),
  }));

  const xAxis = pairs[0]?.vector.lengthSq() ? pairs[0].vector.clone() : new THREE.Vector3(1, 0, 0);
  const yAxis = pairs[1]?.vector.lengthSq() ? pairs[1].vector.clone() : new THREE.Vector3(0, 1, 0);
  let zAxis = pairs[2]?.vector.lengthSq() ? pairs[2].vector.clone() : new THREE.Vector3(0, 0, 1);

  const basis = new THREE.Matrix4().makeBasis(xAxis, yAxis, zAxis);
  if (basis.determinant() < 0) {
    zAxis = zAxis.multiplyScalar(-1);
  }

  const principalBasis = new THREE.Quaternion()
    .setFromRotationMatrix(new THREE.Matrix4().makeBasis(xAxis, yAxis, zAxis))
    .normalize();

  return {
    diagonalInertia: [pairs[0]?.value ?? 0, pairs[1]?.value ?? 0, pairs[2]?.value ?? 0],
    principalAxes: principalBasis.conjugate(),
  };
}

export function computeUsdInertiaProperties(
  inertial: InertialLike | undefined,
): UsdInertiaProperties | null {
  const inertia = inertial?.inertia;
  if (!inertia) {
    return null;
  }

  const originQuaternion = createOriginQuaternion(inertial);
  const hasOffDiagonalTerms =
    sanitizeMoment(inertia.ixy ?? 0) !== 0 ||
    sanitizeMoment(inertia.ixz ?? 0) !== 0 ||
    sanitizeMoment(inertia.iyz ?? 0) !== 0;

  if (!hasOffDiagonalTerms) {
    return {
      diagonalInertia: [
        sanitizeMoment(inertia.ixx ?? 0),
        sanitizeMoment(inertia.iyy ?? 0),
        sanitizeMoment(inertia.izz ?? 0),
      ],
      principalAxesLocal: originQuaternion,
    };
  }

  const matrix = new THREE.Matrix3().set(
    sanitizeMoment(inertia.ixx ?? 0),
    sanitizeMoment(inertia.ixy ?? 0),
    sanitizeMoment(inertia.ixz ?? 0),
    sanitizeMoment(inertia.ixy ?? 0),
    sanitizeMoment(inertia.iyy ?? 0),
    sanitizeMoment(inertia.iyz ?? 0),
    sanitizeMoment(inertia.ixz ?? 0),
    sanitizeMoment(inertia.iyz ?? 0),
    sanitizeMoment(inertia.izz ?? 0),
  );
  const decomposition = MathUtils.computeEigenDecomposition3x3(matrix);
  const principal = buildPrincipalAxes(decomposition.eigenvalues, decomposition.eigenvectors);

  return {
    diagonalInertia: principal.diagonalInertia,
    principalAxesLocal: originQuaternion.clone().multiply(principal.principalAxes).normalize(),
  };
}

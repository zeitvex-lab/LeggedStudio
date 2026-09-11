import * as THREE from 'three';

import type { UrdfVisual } from '@/types';
import type { MeshAnalysis, MeshClearanceObstacle } from '../geometryConversion';

const UNIT_SCALE = new THREE.Vector3(1, 1, 1);
export const LOCAL_Z_AXIS = new THREE.Vector3(0, 0, 1);

export function applyOriginRotationToVector(
  origin: UrdfVisual['origin'] | undefined,
  vector: THREE.Vector3,
): THREE.Vector3 {
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(origin?.rpy?.r ?? 0, origin?.rpy?.p ?? 0, origin?.rpy?.y ?? 0, 'ZYX'),
  );

  return vector.clone().applyQuaternion(quaternion);
}

export function offsetLocalPointByOrigin(
  origin: UrdfVisual['origin'] | undefined,
  localPoint: { x: number; y: number; z: number },
): THREE.Vector3 {
  const rotatedPoint = applyOriginRotationToVector(
    origin,
    new THREE.Vector3(localPoint.x, localPoint.y, localPoint.z),
  );

  return rotatedPoint.add(
    new THREE.Vector3(origin?.xyz?.x ?? 0, origin?.xyz?.y ?? 0, origin?.xyz?.z ?? 0),
  );
}

export function getDirectionAlignmentEuler(direction: THREE.Vector3): THREE.Euler {
  const safeDirection = direction.clone();
  if (safeDirection.lengthSq() <= 1e-12) {
    safeDirection.copy(LOCAL_Z_AXIS);
  } else {
    safeDirection.normalize();
  }

  const quaternion = new THREE.Quaternion().setFromUnitVectors(LOCAL_Z_AXIS, safeDirection);
  return new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');
}

export function createOriginMatrix(origin?: UrdfVisual['origin']): THREE.Matrix4 {
  const matrix = new THREE.Matrix4();
  const position = new THREE.Vector3(origin?.xyz?.x ?? 0, origin?.xyz?.y ?? 0, origin?.xyz?.z ?? 0);
  const quaternion = new THREE.Quaternion().setFromEuler(
    new THREE.Euler(origin?.rpy?.r ?? 0, origin?.rpy?.p ?? 0, origin?.rpy?.y ?? 0, 'ZYX'),
  );
  matrix.compose(position, quaternion, UNIT_SCALE);
  return matrix;
}

export function transformDirectionToWorld(
  linkMatrix: THREE.Matrix4,
  localDirection: THREE.Vector3,
): THREE.Vector3 {
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const position = new THREE.Vector3();
  linkMatrix.decompose(position, quaternion, scale);
  return localDirection.clone().applyQuaternion(quaternion).normalize();
}

export function transformDirectionToLinkFrame(
  linkMatrix: THREE.Matrix4,
  worldDirection: THREE.Vector3,
): THREE.Vector3 {
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  const position = new THREE.Vector3();
  linkMatrix.decompose(position, quaternion, scale);
  return worldDirection.clone().applyQuaternion(quaternion.invert()).normalize();
}

export function transformGeometryToTargetLinkFrame(
  geometry: UrdfVisual,
  sourceLinkMatrix: THREE.Matrix4,
  targetLinkInverseMatrix: THREE.Matrix4,
): UrdfVisual {
  const relativeMatrix = targetLinkInverseMatrix
    .clone()
    .multiply(sourceLinkMatrix)
    .multiply(createOriginMatrix(geometry.origin));
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  relativeMatrix.decompose(position, quaternion, scale);
  const rotation = new THREE.Euler().setFromQuaternion(quaternion, 'ZYX');

  return {
    ...geometry,
    dimensions: geometry.dimensions ? { ...geometry.dimensions } : geometry.dimensions,
    origin: {
      xyz: {
        x: position.x,
        y: position.y,
        z: position.z,
      },
      rpy: {
        r: rotation.x,
        p: rotation.y,
        y: rotation.z,
      },
    },
  };
}

export function transformMeshObstaclePointsToTargetLinkFrame(
  points: NonNullable<MeshAnalysis['surfacePoints']>,
  sourceLinkMatrix: THREE.Matrix4,
  geometryOrigin: UrdfVisual['origin'],
  targetLinkInverseMatrix: THREE.Matrix4,
): MeshClearanceObstacle {
  const transformMatrix = targetLinkInverseMatrix
    .clone()
    .multiply(sourceLinkMatrix)
    .multiply(createOriginMatrix(geometryOrigin));
  const transformedPoint = new THREE.Vector3();

  return {
    points: points.map((point) => {
      transformedPoint.set(point.x, point.y, point.z).applyMatrix4(transformMatrix);
      return {
        x: transformedPoint.x,
        y: transformedPoint.y,
        z: transformedPoint.z,
      };
    }),
  };
}

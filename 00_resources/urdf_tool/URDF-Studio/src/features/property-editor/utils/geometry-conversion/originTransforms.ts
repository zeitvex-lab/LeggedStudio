import * as THREE from 'three';

import { canonicalizeAxis, type Point3 } from '@/core/geometry/primitiveGeometry';
import type { BoxFit } from './primitiveFit';
import type { ConversionResult, MeshPrimaryAxis } from './conversionTypes';

const _tempVec3A = new THREE.Vector3();
const _tempQuat = new THREE.Quaternion();
const _tempQuatB = new THREE.Quaternion();
const _tempEuler = new THREE.Euler(0, 0, 0, 'ZYX');
const _tempEulerB = new THREE.Euler(0, 0, 0, 'ZYX');
const _zAxis = new THREE.Vector3(0, 0, 1);

export function rotateLocalVectorByOrigin(
  origin: ConversionResult['origin'],
  localVector: Point3,
): Point3 {
  _tempEuler.set(origin.rpy.r, origin.rpy.p, origin.rpy.y);
  _tempVec3A.set(localVector.x, localVector.y, localVector.z).applyEuler(_tempEuler);
  const axis = canonicalizeAxis({ x: _tempVec3A.x, y: _tempVec3A.y, z: _tempVec3A.z });
  return axis ?? { x: 0, y: 0, z: 1 };
}

export function offsetOriginByLocalVector(
  origin: ConversionResult['origin'],
  localOffset: { x: number; y: number; z: number },
): ConversionResult['origin'] {
  _tempEuler.set(origin.rpy.r, origin.rpy.p, origin.rpy.y);
  _tempVec3A.set(localOffset.x, localOffset.y, localOffset.z).applyEuler(_tempEuler);

  return {
    xyz: {
      x: origin.xyz.x + _tempVec3A.x,
      y: origin.xyz.y + _tempVec3A.y,
      z: origin.xyz.z + _tempVec3A.z,
    },
    rpy: {
      r: origin.rpy.r,
      p: origin.rpy.p,
      y: origin.rpy.y,
    },
  };
}

export function applyLocalRotationToOrigin(
  origin: ConversionResult['origin'],
  rotation: BoxFit['rotation'],
): ConversionResult['origin'] {
  _tempEuler.set(origin.rpy.r, origin.rpy.p, origin.rpy.y);
  _tempQuat.setFromEuler(_tempEuler);
  _tempQuat.multiply(_tempQuatB.set(rotation.x, rotation.y, rotation.z, rotation.w).normalize());
  _tempEulerB.setFromQuaternion(_tempQuat, 'ZYX');

  return {
    xyz: {
      x: origin.xyz.x,
      y: origin.xyz.y,
      z: origin.xyz.z,
    },
    rpy: {
      r: _tempEulerB.x,
      p: _tempEulerB.y,
      y: _tempEulerB.z,
    },
  };
}

function getAxisAlignmentQuaternion(axis: MeshPrimaryAxis): THREE.Quaternion {
  _tempQuatB.identity();

  if (axis === 'x') {
    _tempQuatB.setFromAxisAngle(_tempVec3A.set(0, 1, 0), Math.PI / 2);
  } else if (axis === 'y') {
    _tempQuatB.setFromAxisAngle(_tempVec3A.set(1, 0, 0), -Math.PI / 2);
  }

  return _tempQuatB;
}

function getDirectionalAlignmentQuaternion(axis: Point3): THREE.Quaternion {
  const normalizedAxis = canonicalizeAxis(axis);
  if (!normalizedAxis) {
    _tempQuatB.identity();
    return _tempQuatB;
  }

  _tempQuatB.setFromUnitVectors(
    _zAxis,
    _tempVec3A.set(normalizedAxis.x, normalizedAxis.y, normalizedAxis.z),
  );
  return _tempQuatB;
}

export function alignOriginToPrimaryAxis(
  origin: ConversionResult['origin'],
  primaryAxis: MeshPrimaryAxis,
): ConversionResult['origin'] {
  if (primaryAxis === 'z') {
    return origin;
  }

  _tempEuler.set(origin.rpy.r, origin.rpy.p, origin.rpy.y);
  _tempQuat.setFromEuler(_tempEuler);
  _tempQuat.multiply(getAxisAlignmentQuaternion(primaryAxis));
  _tempEulerB.setFromQuaternion(_tempQuat, 'ZYX');

  return {
    xyz: {
      x: origin.xyz.x,
      y: origin.xyz.y,
      z: origin.xyz.z,
    },
    rpy: {
      r: _tempEulerB.x,
      p: _tempEulerB.y,
      y: _tempEulerB.z,
    },
  };
}

export function alignOriginToAxis(
  origin: ConversionResult['origin'],
  axis: Point3,
): ConversionResult['origin'] {
  _tempEuler.set(origin.rpy.r, origin.rpy.p, origin.rpy.y);
  _tempQuat.setFromEuler(_tempEuler);
  _tempQuat.multiply(getDirectionalAlignmentQuaternion(axis));
  _tempEulerB.setFromQuaternion(_tempQuat, 'ZYX');

  return {
    xyz: {
      x: origin.xyz.x,
      y: origin.xyz.y,
      z: origin.xyz.z,
    },
    rpy: {
      r: _tempEulerB.x,
      p: _tempEulerB.y,
      y: _tempEulerB.z,
    },
  };
}

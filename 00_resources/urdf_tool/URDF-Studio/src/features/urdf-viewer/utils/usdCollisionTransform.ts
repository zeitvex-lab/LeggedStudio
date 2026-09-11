import * as THREE from 'three';
import type { UrdfVisual } from '@/types';
import { composeUsdGeometryLocalOverrideMatrix } from './usdRuntimeLinkOverrides.ts';

export interface UsdExtractedGeometryTransform {
  position: { x: number; y: number; z: number };
  rotation: { r: number; p: number; y: number };
  scale: { x: number; y: number; z: number };
}

const tempEuler = new THREE.Euler(0, 0, 0, 'ZYX');

export function extractUsdProxyLocalTransformFromWorldMatrices({
  linkWorldMatrix,
  meshWorldMatrix,
}: {
  linkWorldMatrix: THREE.Matrix4;
  meshWorldMatrix: THREE.Matrix4;
}): UsdExtractedGeometryTransform {
  const proxyLocalMatrix = linkWorldMatrix
    .clone()
    .invert()
    .multiply(meshWorldMatrix.clone());

  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  proxyLocalMatrix.decompose(position, quaternion, scale);

  tempEuler.setFromQuaternion(quaternion, 'ZYX');

  return {
    position: { x: position.x, y: position.y, z: position.z },
    rotation: { r: tempEuler.x, p: tempEuler.y, y: tempEuler.z },
    scale: { x: scale.x, y: scale.y, z: scale.z },
  };
}

export function extractUsdGeometryTransformFromWorldMatrix({
  currentGeometry,
  currentMeshWorldMatrix,
  nextMeshWorldMatrix,
  linkWorldMatrix,
}: {
  currentGeometry: UrdfVisual | null | undefined;
  currentMeshWorldMatrix: THREE.Matrix4;
  nextMeshWorldMatrix: THREE.Matrix4;
  linkWorldMatrix: THREE.Matrix4;
}): UsdExtractedGeometryTransform {
  const nextGeometryLocalMatrix = linkWorldMatrix
    .clone()
    .invert()
    .multiply(nextMeshWorldMatrix.clone())
    .multiply(currentMeshWorldMatrix.clone().invert())
    .multiply(linkWorldMatrix.clone())
    .multiply(composeUsdGeometryLocalOverrideMatrix(currentGeometry));

  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  nextGeometryLocalMatrix.decompose(position, quaternion, scale);

  tempEuler.setFromQuaternion(quaternion, 'ZYX');

  return {
    position: { x: position.x, y: position.y, z: position.z },
    rotation: { r: tempEuler.x, p: tempEuler.y, y: tempEuler.z },
    scale: { x: scale.x, y: scale.y, z: scale.z },
  };
}

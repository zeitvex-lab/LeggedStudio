import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import { DEFAULT_LINK } from '@/types';
import {
  composeUsdMeshOverrideWorldMatrix,
  composeUsdMeshOverrideWorldMatrixFromBaseLocal,
} from './usdRuntimeLinkOverrides.ts';
import {
  extractUsdGeometryTransformFromWorldMatrix,
  extractUsdProxyLocalTransformFromWorldMatrices,
} from './usdCollisionTransform.ts';

function toQuaternionFromRpy(rotation: { r: number; p: number; y: number }) {
  return new THREE.Quaternion().setFromEuler(
    new THREE.Euler(rotation.r, rotation.p, rotation.y, 'ZYX'),
  );
}

test('extracts the next USD geometry transform from a dragged mesh world matrix', () => {
  const linkWorldMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(1.5, -0.5, 0.75),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(0.1, -0.2, 0.45)),
    new THREE.Vector3(1, 1, 1),
  );

  const authoredWorldMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(2.25, 0.5, -1.25),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.15, 0.25, 0.05)),
    new THREE.Vector3(1, 1, 1),
  );

  const currentGeometry = {
    ...DEFAULT_LINK.collision,
    origin: {
      xyz: { x: 0.3, y: -0.4, z: 0.9 },
      rpy: { r: 0.2, p: -0.1, y: 0.35 },
    },
    dimensions: { x: 1.4, y: 0.8, z: 1.1 },
  };

  const nextGeometry = {
    ...DEFAULT_LINK.collision,
    origin: {
      xyz: { x: -0.25, y: 0.6, z: 1.15 },
      rpy: { r: -0.05, p: 0.3, y: -0.2 },
    },
    dimensions: currentGeometry.dimensions,
  };

  const currentMeshWorldMatrix = composeUsdMeshOverrideWorldMatrix({
    authoredWorldMatrix,
    geometry: currentGeometry,
    linkWorldMatrix,
  });

  const nextMeshWorldMatrix = composeUsdMeshOverrideWorldMatrix({
    authoredWorldMatrix,
    geometry: nextGeometry,
    linkWorldMatrix,
  });

  const extracted = extractUsdGeometryTransformFromWorldMatrix({
    currentGeometry,
    currentMeshWorldMatrix,
    nextMeshWorldMatrix,
    linkWorldMatrix,
  });

  assert.ok(Math.abs(extracted.position.x - nextGeometry.origin.xyz.x) < 1e-6);
  assert.ok(Math.abs(extracted.position.y - nextGeometry.origin.xyz.y) < 1e-6);
  assert.ok(Math.abs(extracted.position.z - nextGeometry.origin.xyz.z) < 1e-6);

  const expectedQuaternion = toQuaternionFromRpy(nextGeometry.origin.rpy);
  const extractedQuaternion = toQuaternionFromRpy(extracted.rotation);
  assert.ok(expectedQuaternion.angleTo(extractedQuaternion) < 1e-6);
});

test('extractUsdProxyLocalTransformFromWorldMatrices keeps gizmo aligned with residual runtime collision offsets', () => {
  const linkWorldMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(-0.25, 1.2, 0.4),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(0.35, -0.15, 0.2)),
    new THREE.Vector3(1, 1, 1),
  );

  const geometry = {
    ...DEFAULT_LINK.collision,
    origin: {
      xyz: { x: 0.1, y: -0.2, z: 0.45 },
      rpy: { r: 0.05, p: 0.3, y: -0.25 },
    },
    dimensions: { x: 0.7, y: 0.5, z: 1.1 },
  };

  const residualBaseLocalMatrix = new THREE.Matrix4().compose(
    new THREE.Vector3(0.28, -0.12, 0.18),
    new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.2, 0.1, 0.35)),
    new THREE.Vector3(1.1, 0.9, 1.05),
  );

  const currentMeshWorldMatrix = composeUsdMeshOverrideWorldMatrixFromBaseLocal({
    baseLocalMatrix: residualBaseLocalMatrix,
    geometry,
    linkWorldMatrix,
  });

  const proxyLocalTransform = extractUsdProxyLocalTransformFromWorldMatrices({
    linkWorldMatrix,
    meshWorldMatrix: currentMeshWorldMatrix,
  });

  const recomposedProxyWorldMatrix = linkWorldMatrix.clone().multiply(
    new THREE.Matrix4().compose(
      new THREE.Vector3(
        proxyLocalTransform.position.x,
        proxyLocalTransform.position.y,
        proxyLocalTransform.position.z,
      ),
      toQuaternionFromRpy(proxyLocalTransform.rotation),
      new THREE.Vector3(
        proxyLocalTransform.scale.x,
        proxyLocalTransform.scale.y,
        proxyLocalTransform.scale.z,
      ),
    ),
  );

  const currentMeshWorldPosition = new THREE.Vector3();
  const recomposedProxyWorldPosition = new THREE.Vector3();
  currentMeshWorldMatrix.decompose(
    currentMeshWorldPosition,
    new THREE.Quaternion(),
    new THREE.Vector3(),
  );
  recomposedProxyWorldMatrix.decompose(
    recomposedProxyWorldPosition,
    new THREE.Quaternion(),
    new THREE.Vector3(),
  );

  const positionDelta = currentMeshWorldPosition.distanceTo(recomposedProxyWorldPosition);
  assert.ok(positionDelta < 1e-6, `proxy world position should match runtime mesh world position (delta ${positionDelta})`);
  assert.ok(
    Math.abs(proxyLocalTransform.position.x - geometry.origin.xyz.x) > 1e-3
      || Math.abs(proxyLocalTransform.position.y - geometry.origin.xyz.y) > 1e-3
      || Math.abs(proxyLocalTransform.position.z - geometry.origin.xyz.z) > 1e-3,
    'proxy local position should include the residual runtime offset instead of mirroring the authored collision origin',
  );
});

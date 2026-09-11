import test from 'node:test';
import assert from 'node:assert/strict';
import { JointType } from '@/types';
import {
  BRIDGE_PREVIEW_ID,
  bridgeEulerDegreesToQuaternion,
  bridgeQuaternionToEulerDegrees,
  buildBridgePreview,
  normalizeBridgeQuaternion,
} from './bridgePreview.ts';

test('bridgeEulerDegreesToQuaternion converts URDF ZYX euler degrees into normalized XYZW quaternion', () => {
  const quaternion = bridgeEulerDegreesToQuaternion({ r: 0, p: 0, y: 90 });

  assert.ok(Math.abs(quaternion.x) < 1e-6);
  assert.ok(Math.abs(quaternion.y) < 1e-6);
  assert.ok(Math.abs(quaternion.z - Math.sqrt(0.5)) < 1e-6);
  assert.ok(Math.abs(quaternion.w - Math.sqrt(0.5)) < 1e-6);
});

test('bridgeQuaternionToEulerDegrees maps normalized quaternions back to display degrees', () => {
  const eulerDegrees = bridgeQuaternionToEulerDegrees({
    x: 0,
    y: 0,
    z: Math.sqrt(0.5),
    w: Math.sqrt(0.5),
  });

  assert.ok(Math.abs(eulerDegrees.r) < 1e-6);
  assert.ok(Math.abs(eulerDegrees.p) < 1e-6);
  assert.ok(Math.abs(eulerDegrees.y - 90) < 1e-6);
});

test('normalizeBridgeQuaternion falls back to identity for zero-length input', () => {
  assert.deepEqual(normalizeBridgeQuaternion({ x: 0, y: 0, z: 0, w: 0 }), {
    x: 0,
    y: 0,
    z: 0,
    w: 1,
  });
});

test('buildBridgePreview includes quaternion metadata derived from euler degrees', () => {
  const preview = buildBridgePreview({
    name: 'preview_joint',
    parentComponentId: 'comp_a',
    parentLinkId: 'base_link',
    childComponentId: 'comp_b',
    childLinkId: 'tool_link',
    jointType: JointType.FIXED,
    originXyz: { x: 0.1, y: -0.05, z: 0.2 },
    axis: { x: 0, y: 0, z: 1 },
    limitLower: -1.57,
    limitUpper: 1.57,
    rotationMode: 'euler_deg',
    rotationEulerDeg: { r: 0, p: 0, y: 90 },
    rotationQuaternion: { x: 0, y: 0, z: 0, w: 1 },
  });

  assert.ok(preview);
  assert.equal(preview?.id, BRIDGE_PREVIEW_ID);
  assert.equal(preview?.joint.origin.xyz.x, 0.1);
  assert.ok(Math.abs((preview?.joint.origin.rpy.y ?? 0) - Math.PI / 2) < 1e-6);
  assert.ok(Math.abs((preview?.joint.origin.quatXyzw?.z ?? 0) - Math.sqrt(0.5)) < 1e-6);
  assert.ok(Math.abs((preview?.joint.origin.quatXyzw?.w ?? 0) - Math.sqrt(0.5)) < 1e-6);
});

test('buildBridgePreview keeps continuous joints limited to effort and velocity only', () => {
  const preview = buildBridgePreview({
    name: 'spin_joint',
    parentComponentId: 'comp_a',
    parentLinkId: 'base_link',
    childComponentId: 'comp_b',
    childLinkId: 'tool_link',
    jointType: JointType.CONTINUOUS,
    hardwareInterface: 'velocity',
    originXyz: { x: 0, y: 0, z: 0 },
    axis: { x: 0, y: 0, z: 1 },
    limitLower: -1.57,
    limitUpper: 1.57,
    limitEffort: 35,
    limitVelocity: 12,
    rotationMode: 'euler_deg',
    rotationEulerDeg: { r: 0, p: 0, y: 0 },
    rotationQuaternion: { x: 0, y: 0, z: 0, w: 1 },
  });

  assert.ok(preview);
  assert.deepEqual(preview?.joint.limit, {
    effort: 35,
    velocity: 12,
  });
  assert.equal('lower' in (preview?.joint.limit ?? {}), false);
  assert.equal('upper' in (preview?.joint.limit ?? {}), false);
  assert.equal(preview?.joint.hardware.hardwareInterface, 'velocity');
});

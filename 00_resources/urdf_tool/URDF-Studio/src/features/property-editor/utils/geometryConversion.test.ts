import assert from 'node:assert/strict';
import test from 'node:test';

import { GeometryType } from '@/types';

import { convertGeometryType } from './geometryConversion';

const ROTATED_ORIGIN = {
  xyz: { x: 0.12, y: -0.08, z: 0.21 },
  rpy: { r: 0.37, p: -0.42, y: 0.58 },
} as const;

test('mesh to cylinder preserves authored collision rotation when primitive fit exists', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CYLINDER,
    {
      bounds: {
        x: 0.82,
        y: 0.21,
        z: 0.18,
        cx: 0,
        cy: 0,
        cz: 0,
      },
      primitiveFits: {
        cylinder: {
          axis: { x: 1, y: 0, z: 0 },
          center: { x: 0, y: 0, z: 0 },
          radius: 0.09,
          length: 0.8,
          volume: 0.020357520395261863,
        },
      },
    },
  );

  assert.deepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
});

test('mesh to cylinder prefers the fit that matches the existing local axis instead of rotating the collider', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CYLINDER,
    {
      bounds: {
        x: 0.82,
        y: 0.21,
        z: 0.18,
        cx: 0,
        cy: 0,
        cz: 0,
      },
      primitiveFits: {
        cylinder: {
          axis: { x: 1, y: 0, z: 0 },
          center: { x: 0, y: 0, z: 0 },
          radius: 0.07,
          length: 0.92,
          volume: 0.014185086476958216,
        },
        cylinderCandidates: [
          {
            axis: { x: 1, y: 0, z: 0 },
            center: { x: 0, y: 0, z: 0 },
            radius: 0.07,
            length: 0.92,
            volume: 0.014185086476958216,
          },
          {
            axis: { x: 0, y: 0, z: 1 },
            center: { x: 0, y: 0, z: 0 },
            radius: 0.16,
            length: 0.48,
            volume: 0.03860424498338151,
          },
        ],
      },
    },
  );

  assert.deepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
  assert.deepEqual(converted.dimensions, {
    x: 0.16,
    y: 0.48,
    z: 0.16,
  });
});

test('mesh to capsule preserves authored collision rotation when primitive fit exists', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CAPSULE,
    {
      bounds: {
        x: 0.82,
        y: 0.21,
        z: 0.18,
        cx: 0,
        cy: 0,
        cz: 0,
      },
      primitiveFits: {
        capsule: {
          axis: { x: 0, y: 1, z: 0 },
          center: { x: 0, y: 0, z: 0 },
          radius: 0.08,
          length: 0.7,
          volume: 0.016956754390741893,
        },
      },
    },
  );

  assert.deepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
});

test('mesh to cylinder fallback sizing preserves authored collision rotation without primitive fit', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CYLINDER,
    {
      bounds: {
        x: 0.91,
        y: 0.23,
        z: 0.19,
        cx: 0.04,
        cy: -0.02,
        cz: 0.01,
      },
    },
  );

  assert.deepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
});

test('mesh to capsule fallback sizing preserves authored collision rotation without primitive fit', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CAPSULE,
    {
      bounds: {
        x: 0.91,
        y: 0.23,
        z: 0.19,
        cx: 0.04,
        cy: -0.02,
        cz: 0.01,
      },
    },
  );

  assert.deepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
});

test('mesh to box uses the tighter fitted box when the mesh fit is materially smaller than the raw bounds', () => {
  const rotatedHalfYaw = Math.PI / 8;
  const converted = convertGeometryType(
    {
      type: GeometryType.MESH,
      origin: ROTATED_ORIGIN,
    },
    GeometryType.BOX,
    {
      bounds: {
        x: 0.84,
        y: 0.44,
        z: 0.24,
        cx: 0,
        cy: 0,
        cz: 0,
      },
      primitiveFits: {
        box: {
          center: { x: 0.03, y: -0.01, z: 0.02 },
          dimensions: { x: 0.56, y: 0.19, z: 0.18 },
          rotation: {
            x: 0,
            y: Math.sin(rotatedHalfYaw),
            z: 0,
            w: Math.cos(rotatedHalfYaw),
          },
          volume: 0.019152,
        },
      },
    },
  );

  assert.deepEqual(converted.dimensions, {
    x: 0.56,
    y: 0.19,
    z: 0.18,
  });
  assert.notDeepEqual(converted.origin.rpy, ROTATED_ORIGIN.rpy);
});

test('box to cylinder keeps the cylinder radius close to the source box cross section', () => {
  const converted = convertGeometryType(
    {
      type: GeometryType.BOX,
      dimensions: { x: 0.6, y: 0.2, z: 1 },
      origin: ROTATED_ORIGIN,
    },
    GeometryType.CYLINDER,
  );

  assert.ok(Math.abs(converted.dimensions.x - Math.sqrt(0.6 * 0.2) / 2) <= 1e-9);
  assert.equal(converted.dimensions.y, 1);
});

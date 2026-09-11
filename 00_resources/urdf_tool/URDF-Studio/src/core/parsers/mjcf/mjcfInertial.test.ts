import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { createEmptyLinkInertial, deriveGeomMassInertial } from './mjcfInertial';

describe('mjcfInertial', () => {
  describe('createEmptyLinkInertial', () => {
    it('returns a zeroed inertial at the origin', () => {
      const inertial = createEmptyLinkInertial();
      assert.equal(inertial.mass, 0);
      assert.deepEqual(inertial.origin, {
        xyz: { x: 0, y: 0, z: 0 },
        rpy: { r: 0, p: 0, y: 0 },
      });
      assert.deepEqual(inertial.inertia, {
        ixx: 0,
        ixy: 0,
        ixz: 0,
        iyy: 0,
        iyz: 0,
        izz: 0,
      });
    });

    it('returns a fresh object each call (no shared mutable state)', () => {
      const first = createEmptyLinkInertial();
      const second = createEmptyLinkInertial();
      assert.notEqual(first, second);
      assert.notEqual(first.inertia, second.inertia);
    });
  });

  describe('deriveGeomMassInertial', () => {
    it('returns null when no geom carries positive mass', () => {
      assert.equal(deriveGeomMassInertial([]), null);
      assert.equal(deriveGeomMassInertial([{ mass: 0 }, { mass: -1 }]), null);
      assert.equal(deriveGeomMassInertial([{ pos: { x: 1, y: 2, z: 3 } }]), null);
      assert.equal(deriveGeomMassInertial([{ mass: Number.NaN }]), null);
    });

    it('places the center of mass at the single massive geom position', () => {
      const result = deriveGeomMassInertial([{ mass: 2, pos: { x: 1, y: 0, z: 0 } }]);
      assert.ok(result?.origin);
      assert.equal(result.mass, 2);
      assert.deepEqual(result.origin.xyz, { x: 1, y: 0, z: 0 });
      // A point mass about its own center contributes zero inertia.
      assert.deepEqual(result.inertia, {
        ixx: 0,
        ixy: 0,
        ixz: 0,
        iyy: 0,
        iyz: 0,
        izz: 0,
      });
    });

    it('mass-weights the center of mass across geoms', () => {
      const result = deriveGeomMassInertial([
        { mass: 1, pos: { x: 0, y: 0, z: 0 } },
        { mass: 3, pos: { x: 4, y: 0, z: 0 } },
      ]);
      assert.ok(result?.origin);
      assert.equal(result.mass, 4);
      // (1*0 + 3*4) / 4 = 3
      assert.equal(result.origin.xyz.x, 3);
    });

    it('derives the parallel-axis inertia of two point masses on the x-axis', () => {
      const result = deriveGeomMassInertial([
        { mass: 1, pos: { x: -1, y: 0, z: 0 } },
        { mass: 1, pos: { x: 1, y: 0, z: 0 } },
      ]);
      assert.ok(result?.origin);
      assert.equal(result.origin.xyz.x, 0);
      // Two unit masses at x = ±1: ixx = 0 (no y/z offset), iyy = izz = 2.
      assert.equal(result.inertia.ixx, 0);
      assert.equal(result.inertia.iyy, 2);
      assert.equal(result.inertia.izz, 2);
      assert.equal(result.inertia.ixy, 0);
      assert.equal(result.inertia.ixz, 0);
      assert.equal(result.inertia.iyz, 0);
    });

    it('uses the fromto midpoint when a geom has no explicit pos', () => {
      const result = deriveGeomMassInertial([
        { mass: 5, fromto: [0, 0, 0, 2, 0, 0] },
      ]);
      assert.ok(result?.origin);
      assert.equal(result.mass, 5);
      assert.deepEqual(result.origin.xyz, { x: 1, y: 0, z: 0 });
    });

    it('ignores zero/negative/non-finite mass geoms in the aggregate', () => {
      const result = deriveGeomMassInertial([
        { mass: 0, pos: { x: 100, y: 0, z: 0 } },
        { mass: -2, pos: { x: -100, y: 0, z: 0 } },
        { mass: 4, pos: { x: 2, y: 0, z: 0 } },
      ]);
      assert.ok(result?.origin);
      assert.equal(result.mass, 4);
      assert.equal(result.origin.xyz.x, 2);
    });
  });
});

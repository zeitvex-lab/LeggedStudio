import test from 'node:test';
import assert from 'node:assert/strict';

import { JSDOM } from 'jsdom';
import * as THREE from 'three';

import { parseMJCFModel } from './mjcfModel.ts';
import { createCanonicalSnapshotFromParsedModel } from './mjcfSnapshot.ts';

function installDomGlobals(): void {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { contentType: 'text/html' });
  globalThis.window = dom.window as any;
  globalThis.document = dom.window.document as any;
  globalThis.DOMParser = dom.window.DOMParser as any;
  globalThis.XMLSerializer = dom.window.XMLSerializer as any;
  globalThis.Node = dom.window.Node as any;
  globalThis.Element = dom.window.Element as any;
  globalThis.Document = dom.window.Document as any;
}

function assertCloseArray(
  actual: number[] | null | undefined,
  expected: number[],
  tolerance: number = 1e-5,
): void {
  assert.ok(actual, 'expected array to be defined');
  assert.equal(actual.length, expected.length);
  actual.forEach((value, index) => {
    assert.ok(
      Math.abs(value - expected[index]!) <= tolerance,
      `index ${index}: expected ${expected[index]}, got ${value}`,
    );
  });
}

function assertQuaternionClose(
  actual: [number, number, number, number] | null | undefined,
  expected: [number, number, number, number],
  tolerance: number = 1e-5,
): void {
  assert.ok(actual, 'expected quaternion to be defined');
  const direct = actual.every((value, index) => Math.abs(value - expected[index]!) <= tolerance);
  const negated = actual.every((value, index) => Math.abs(value + expected[index]!) <= tolerance);
  assert.ok(
    direct || negated,
    `expected quaternion ${expected.join(', ')}, got ${actual.join(', ')}`,
  );
}

function inertiaTensorFromBody(
  inertia: [number, number, number] | null | undefined,
  quat: [number, number, number, number] | null | undefined,
): [number, number, number, number, number, number] | null {
  if (!inertia) {
    return null;
  }

  const [w, x, y, z] = quat || [1, 0, 0, 0];
  const rotation = new THREE.Matrix4().makeRotationFromQuaternion(
    new THREE.Quaternion(x, y, z, w).normalize(),
  );
  const basisX = new THREE.Vector3().setFromMatrixColumn(rotation, 0);
  const basisY = new THREE.Vector3().setFromMatrixColumn(rotation, 1);
  const basisZ = new THREE.Vector3().setFromMatrixColumn(rotation, 2);
  const [ix, iy, iz] = inertia;

  return [
    basisX.x * basisX.x * ix + basisY.x * basisY.x * iy + basisZ.x * basisZ.x * iz,
    basisX.y * basisX.y * ix + basisY.y * basisY.y * iy + basisZ.y * basisZ.y * iz,
    basisX.z * basisX.z * ix + basisY.z * basisY.z * iy + basisZ.z * basisZ.z * iz,
    basisX.x * basisX.y * ix + basisY.x * basisY.y * iy + basisZ.x * basisZ.y * iz,
    basisX.x * basisX.z * ix + basisY.x * basisY.z * iy + basisZ.x * basisZ.z * iz,
    basisX.y * basisX.z * ix + basisY.y * basisY.z * iy + basisZ.y * basisZ.z * iz,
  ];
}

test('canonical snapshot diagonalizes fullinertia like MuJoCo', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="inertia">
          <worldbody>
            <body name="cassie-pelvis">
              <inertial pos="0 0 0" mass="1" fullinertia="0.085821 0.049222 0.08626 1.276e-05 -0.00016022 -0.000414" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const body = snapshot.bodies.find((entry) => entry.key === 'cassie-pelvis');

  assert.ok(body);
  assertCloseArray(body.inertia, [0.086317, 0.085769, 0.049217], 1e-4);
  assertCloseArray(
    inertiaTensorFromBody(body.inertia, body.inertialQuat),
    [0.085821, 0.049222, 0.08626, 1.276e-5, -0.00016022, -0.000414],
    1e-4,
  );
});

test('canonical snapshot normalizes fromto capsules into pos/quat/half-length size', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="fromto">
          <worldbody>
            <body name="left-leg">
              <geom type="capsule" size="0.08" fromto="0 0 -0.05 0.12 0 -0.05" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const geom = snapshot.geoms.find((entry) => entry.bodyKey === 'left-leg');

  assert.ok(geom);
  assertCloseArray(geom.size, [0.08, 0.06], 1e-6);
  assertCloseArray(geom.pos, [0.06, 0, -0.05], 1e-6);
  assertQuaternionClose(geom.quat, [0.70710678, 0, -0.70710678, 0], 1e-5);
});

test('canonical snapshot matches MuJoCo fromto cylinder orientation when already pointing up', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="fromto-z">
          <worldbody>
            <body name="column">
              <geom type="cylinder" size="0.08" fromto="0 0 -0.01 0 0 0.195" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const geom = snapshot.geoms.find((entry) => entry.bodyKey === 'column');

  assert.ok(geom);
  assertCloseArray(geom.pos, [0, 0, 0.0925], 1e-6);
  assertQuaternionClose(geom.quat, [0, 1, 0, 0], 1e-6);
});

test('canonical snapshot trims geom size vectors to the effective MuJoCo type arity', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="geom-size-arity">
          <worldbody>
            <body name="body">
              <geom name="ball" size="0.057 0.04675 0.057" />
              <geom name="roller" type="cylinder" size="0.02 0.04 0.04" />
              <geom name="pad" type="capsule" size="0.009 0.012 0.008" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const ball = snapshot.geoms.find((entry) => entry.key === 'ball');
  const roller = snapshot.geoms.find((entry) => entry.key === 'roller');
  const pad = snapshot.geoms.find((entry) => entry.key === 'pad');

  assert.ok(ball);
  assert.ok(roller);
  assert.ok(pad);
  assert.deepEqual(ball.size, [0.057]);
  assert.deepEqual(roller.size, [0.02, 0.04]);
  assert.deepEqual(pad.size, [0.009, 0.012]);
});

test('canonical snapshot normalizes joint axes to unit vectors', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="joint-axis">
          <worldbody>
            <body name="neck">
              <joint name="neck_rotation" type="hinge" axis="0.2 1 0" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const joint = snapshot.joints.find((entry) => entry.key === 'neck_rotation');

  assert.ok(joint);
  assertCloseArray(joint.axis, [0.196116, 0.980581, 0], 1e-6);
});

test('canonical snapshot uses underscore-based fallback keys for anonymous MJCF bodies and joints', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="anonymous-canonical-keys">
          <worldbody>
            <body>
              <joint type="hinge" axis="0 0 1" />
              <geom type="sphere" size="0.02" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);

  assert.ok(snapshot.bodies.find((entry) => entry.key === 'world_body_0'));
  assert.ok(snapshot.joints.find((entry) => entry.key === 'world_body_0_joint_0'));
  assert.ok(snapshot.geoms.find((entry) => entry.key === 'world_body_0_geom_0'));
});

test('canonical snapshot applies compiler boundinertia when diagonalizing tiny fullinertia', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="boundinertia">
          <compiler boundinertia="0.0001" />
          <worldbody>
            <body name="thumb">
              <inertial
                pos="0 0 0"
                mass="0.003"
                fullinertia="5e-08 3e-08 5e-08 1e-08 1e-08 -1e-08"
              />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const body = snapshot.bodies.find((entry) => entry.key === 'thumb');

  assert.ok(body);
  assertCloseArray(body.inertia, [0.0001, 0.0001, 0.0001], 1e-8);
});

test('canonical snapshot applies compiler boundinertia to explicit diaginertia', () => {
  installDomGlobals();
  const parsedModel = parseMJCFModel(`
        <mujoco model="boundinertia-diag">
          <compiler boundinertia="0.0001" />
          <worldbody>
            <body name="ball">
              <inertial pos="0 0 0" mass="0.0027" diaginertia="0.00000072 0.00000072 0.00000072" />
            </body>
          </worldbody>
        </mujoco>
    `);

  assert.ok(parsedModel);
  const snapshot = createCanonicalSnapshotFromParsedModel(parsedModel);
  const body = snapshot.bodies.find((entry) => entry.key === 'ball');

  assert.ok(body);
  assertCloseArray(body.inertia, [0.0001, 0.0001, 0.0001], 1e-8);
});

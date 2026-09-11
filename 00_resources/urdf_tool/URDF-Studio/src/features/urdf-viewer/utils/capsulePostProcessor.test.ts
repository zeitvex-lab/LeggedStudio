import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { JSDOM } from 'jsdom';

import { URDFLink } from '@/core/parsers/urdf/loader/URDFClasses';

import { processCapsuleGeometries } from './capsulePostProcessor';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;

test('processCapsuleGeometries disposes generated matte materials before replacing collision capsule materials', () => {
  const robot = new THREE.Group();
  const link = new URDFLink();
  link.name = 'base_link';
  robot.add(link);

  const originalDispose = THREE.Material.prototype.dispose;
  let disposeCalls = 0;
  THREE.Material.prototype.dispose = function patchedDispose(this: THREE.Material) {
    disposeCalls += 1;
    return originalDispose.call(this);
  };

  try {
    processCapsuleGeometries(robot, `<?xml version="1.0"?>
<robot name="capsule_test">
  <link name="base_link">
    <collision>
      <geometry>
        <capsule radius="0.1" length="0.6" />
      </geometry>
    </collision>
  </link>
</robot>`);
  } finally {
    THREE.Material.prototype.dispose = originalDispose;
  }

  assert.equal(disposeCalls, 3);
});

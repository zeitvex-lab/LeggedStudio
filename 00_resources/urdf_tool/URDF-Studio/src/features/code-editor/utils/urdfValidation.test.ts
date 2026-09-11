import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

import { validateUrdfDocument } from './urdfValidation.ts';

globalThis.DOMParser = new JSDOM('').window.DOMParser as typeof DOMParser;

test('reports unknown tags that are not part of the URDF schema', () => {
  const errors = validateUrdfDocument(`<?xml version="1.0"?>
<robot name="demo">
  <foo />
</robot>`);

  assert.ok(errors.some((error) => error.message.includes('Unknown <foo> element')));
});

test('reports invalid enumerated joint types from the URDF schema', () => {
  const errors = validateUrdfDocument(`<?xml version="1.0"?>
<robot name="demo">
  <link name="base" />
  <link name="tip" />
  <joint name="bad_joint" type="spinny">
    <parent link="base" />
    <child link="tip" />
  </joint>
</robot>`);

  assert.ok(errors.some((error) => error.message.includes('invalid value "spinny"')));
});

test('reports missing required attributes defined by the URDF schema', () => {
  const errors = validateUrdfDocument(`<?xml version="1.0"?>
<robot name="demo">
  <link name="base">
    <visual>
      <geometry>
        <mesh />
      </geometry>
    </visual>
  </link>
</robot>`);

  assert.ok(errors.some((error) => error.message.includes('missing required "filename" attribute')));
});

test('accepts optional visual name metadata from the URDF schema', () => {
  const errors = validateUrdfDocument(`<?xml version="1.0"?>
<robot name="demo" version="1.1">
  <link name="base" type="rigid">
    <visual name="base_visual">
      <geometry>
        <box size="1 1 1" />
      </geometry>
    </visual>
  </link>
</robot>`);

  assert.equal(errors.length, 0);
});

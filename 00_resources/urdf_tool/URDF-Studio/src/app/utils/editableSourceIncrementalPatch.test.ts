import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import { parseMJCF, parseURDF } from '@/core/parsers';

import { applyEditableSourceIncrementalPatch } from './editableSourceIncrementalPatch';
import {
  detectEditableSourceIncrementalPatch,
  detectEditableSourceIncrementalPatchWithDiagnostics,
} from './editableSourceIncrementalPatchDetection';

const { window } = new JSDOM();

if (!globalThis.DOMParser) {
  globalThis.DOMParser = window.DOMParser;
}

const URDF_LINK_FIXTURE = `<?xml version="1.0"?>
<robot name="demo_robot">
  <link name="base_link">
    <visual>
      <origin xyz="0 0 0.25" rpy="0 0 0" />
      <geometry>
        <cylinder radius="0.05" length="0.5" />
      </geometry>
      <material name="base_link_mat">
        <color rgba="0.94902353 0.94118039 0.90980784 1.00000000"/>
      </material>
    </visual>
    <collision>
      <origin xyz="0 0 0.25" rpy="0 0 0" />
      <geometry>
        <cylinder radius="0.05" length="0.5" />
      </geometry>
    </collision>
  </link>
</robot>`;

const URDF_JOINT_FIXTURE = `<?xml version="1.0"?>
<robot name="joint_robot">
  <link name="base_link" />
  <link name="arm_link" />
  <joint name="shoulder_joint" type="revolute">
    <parent link="base_link" />
    <child link="arm_link" />
    <origin xyz="0 0 0.5" rpy="0 0 0" />
    <axis xyz="0 0 1" />
    <limit lower="-1.57" upper="1.57" effort="100" velocity="10" />
    <dynamics damping="0" friction="0" />
  </joint>
</robot>`;

const MJCF_FIXTURE = `<mujoco model="mjcf_patch_demo">
  <worldbody>
    <body name="base_link">
      <geom type="box" size="0.1 0.1 0.1" />
      <body name="foot_link" pos="0 0 0.1">
        <joint name="foot_joint" type="hinge" axis="0 1 0" range="-1 1" damping="0" />
        <geom type="sphere" size="0.0165" rgba="0.8 0.8 0.8 1" />
      </body>
    </body>
  </worldbody>
</mujoco>`;

test('detectEditableSourceIncrementalPatch detects and applies a URDF link fragment update', () => {
  const currentState = parseURDF(URDF_LINK_FIXTURE);
  assert.ok(currentState, 'expected URDF fixture to parse');

  const nextContent = URDF_LINK_FIXTURE.replace('length="0.5"', 'length="1"');
  const dirtyStart = nextContent.indexOf('length="1"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_LINK_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'length="1"'.length }],
  });
  const patchedState = patch
    ? applyEditableSourceIncrementalPatch({
        patch,
        currentState,
      })
    : null;

  assert.equal(patch?.kind, 'urdf-link-fragment-update');
  assert.equal(patch?.previousLinkName, 'base_link');
  assert.ok(patchedState);
  assert.equal(patchedState?.links.base_link.id, 'base_link');
  assert.equal(patchedState?.links.base_link.visual.dimensions.y, 1);
  assert.equal(currentState?.links.base_link.visual.dimensions.y, 0.5);
});

test('detectEditableSourceIncrementalPatch detects and applies a URDF joint fragment update', () => {
  const currentState = parseURDF(URDF_JOINT_FIXTURE);
  assert.ok(currentState, 'expected URDF joint fixture to parse');

  const nextContent = URDF_JOINT_FIXTURE.replace('damping="0"', 'damping="0.2"');
  const dirtyStart = nextContent.indexOf('damping="0.2"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_JOINT_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'damping="0.2"'.length }],
  });
  const patchedState = patch
    ? applyEditableSourceIncrementalPatch({
        patch,
        currentState,
      })
    : null;

  assert.equal(patch?.kind, 'urdf-joint-fragment-update');
  assert.equal(patch?.previousJointName, 'shoulder_joint');
  assert.ok(patchedState);
  assert.equal(patchedState?.joints.shoulder_joint.id, 'shoulder_joint');
  assert.equal(patchedState?.joints.shoulder_joint.dynamics.damping, 0.2);
  assert.equal(currentState?.joints.shoulder_joint.dynamics.damping, 0);
});

test('detectEditableSourceIncrementalPatch detects and applies an MJCF body subtree update', () => {
  const currentState = parseMJCF(MJCF_FIXTURE);
  assert.ok(currentState, 'expected MJCF fixture to parse');

  const nextContent = MJCF_FIXTURE.replace('size="0.0165"', 'size="0.03"');
  const dirtyStart = nextContent.indexOf('size="0.03"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.xml', format: 'mjcf' },
    previousContent: MJCF_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'size="0.03"'.length }],
  });
  const patchedState = patch
    ? applyEditableSourceIncrementalPatch({
        patch,
        currentState,
      })
    : null;

  assert.equal(patch?.kind, 'mjcf-body-subtree-update');
  assert.deepEqual(patch?.stableLinkNames, ['foot_link']);
  assert.deepEqual(patch?.stableJointNames, ['foot_joint']);
  assert.ok(patchedState);
  assert.equal(patchedState?.links.foot_link.id, 'foot_link');
  assert.equal(patchedState?.links.foot_link.visual.dimensions.x, 0.03);
  assert.equal(currentState?.links.foot_link.visual.dimensions.x, 0.0165);
});

test('applyEditableSourceIncrementalPatch applies an MJCF body joint patch without changing stable joint ids', () => {
  const currentState = parseMJCF(MJCF_FIXTURE);
  assert.ok(currentState, 'expected MJCF fixture to parse');

  const nextContent = MJCF_FIXTURE.replace('damping="0"', 'damping="0.2"');
  const dirtyStart = nextContent.indexOf('damping="0.2"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.xml', format: 'mjcf' },
    previousContent: MJCF_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'damping="0.2"'.length }],
  });
  const patchedState = patch
    ? applyEditableSourceIncrementalPatch({
        patch,
        currentState,
      })
    : null;

  assert.ok(patchedState);
  assert.equal(patchedState?.joints.foot_joint.id, 'foot_joint');
  assert.equal(patchedState?.joints.foot_joint.dynamics.damping, 0.2);
  assert.equal(currentState?.joints.foot_joint.dynamics.damping, 0);
});

test('detectEditableSourceIncrementalPatch returns null for MJCF structural subtree changes', () => {
  const nextContent = MJCF_FIXTURE.replace(
    '<geom type="sphere" size="0.0165" rgba="0.8 0.8 0.8 1" />',
    [
      '<geom type="sphere" size="0.0165" rgba="0.8 0.8 0.8 1" />',
      '<geom type="sphere" size="0.01" rgba="0.2 0.2 0.2 1" />',
    ].join('\n        '),
  );
  const dirtyStart = nextContent.indexOf('size="0.01"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.xml', format: 'mjcf' },
    previousContent: MJCF_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'size="0.01"'.length }],
  });

  assert.equal(patch, null);
});

test('detectEditableSourceIncrementalPatch returns null when dirty ranges span multiple URDF elements', () => {
  const nextContent = URDF_JOINT_FIXTURE.replace('name="base_link"', 'name="base_root"').replace(
    'damping="0"',
    'damping="0.2"',
  );
  const linkDirtyStart = nextContent.indexOf('name="base_root"');
  const jointDirtyStart = nextContent.indexOf('damping="0.2"');
  assert.notEqual(linkDirtyStart, -1);
  assert.notEqual(jointDirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_JOINT_FIXTURE,
    nextContent,
    dirtyRanges: [
      { startOffset: linkDirtyStart, endOffset: linkDirtyStart + 'name="base_root"'.length },
      { startOffset: jointDirtyStart, endOffset: jointDirtyStart + 'damping="0.2"'.length },
    ],
  });

  assert.equal(patch, null);
});

test('detectEditableSourceIncrementalPatchWithDiagnostics explains large source edits as full-parse work', () => {
  const injectedLinks = Array.from({ length: 8 }, (_, index) => {
    const linkName = `extra_link_${index}`;
    return `<link name="${linkName}"><visual><geometry><box size="1 1 1" /></geometry></visual></link>`;
  }).join('\n  ');
  const nextContent = URDF_JOINT_FIXTURE.replace(
    '</robot>',
    `  ${injectedLinks}\n</robot>`,
  );
  const dirtyStart = nextContent.indexOf('<link name="extra_link_0"');
  assert.notEqual(dirtyStart, -1);

  const result = detectEditableSourceIncrementalPatchWithDiagnostics({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_JOINT_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: nextContent.indexOf('</robot>') }],
  });

  assert.equal(result.patch, null);
  assert.equal(result.diagnostics.skipReason, 'dirty-span-too-large');
  assert.equal(result.diagnostics.patchKind, null);
  assert.equal(result.diagnostics.dirtyRangeCount, 1);
  assert.ok(result.diagnostics.dirtySpanBytes > result.diagnostics.dirtySpanLimitBytes);
});

test('detectEditableSourceIncrementalPatchWithDiagnostics skips scattered small edits', () => {
  const nextContent = URDF_JOINT_FIXTURE
    .replace('name="base_link"', 'name="base_root"')
    .replace('name="arm_link"', 'name="arm_tip"')
    .replace('lower="-1.57"', 'lower="-1.56"')
    .replace('upper="1.57"', 'upper="1.56"')
    .replace('velocity="10"', 'velocity="11"');

  const dirtyRanges = [
    'name="base_root"',
    'name="arm_tip"',
    'lower="-1.56"',
    'upper="1.56"',
    'velocity="11"',
  ].map((token) => {
    const startOffset = nextContent.indexOf(token);
    assert.notEqual(startOffset, -1);
    return { startOffset, endOffset: startOffset + token.length };
  });

  const result = detectEditableSourceIncrementalPatchWithDiagnostics({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_JOINT_FIXTURE,
    nextContent,
    dirtyRanges,
  });

  assert.equal(result.patch, null);
  assert.equal(result.diagnostics.skipReason, 'too-many-dirty-ranges');
  assert.equal(result.diagnostics.dirtyRangeCount, 5);
});

test('detectEditableSourceIncrementalPatch skips MJCF patches when requested', () => {
  const nextContent = MJCF_FIXTURE.replace('size="0.0165"', 'size="0.03"');
  const dirtyStart = nextContent.indexOf('size="0.03"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.xml', format: 'mjcf' },
    previousContent: MJCF_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'size="0.03"'.length }],
    skipMjcfPatch: true,
  });

  assert.equal(patch, null);
});

test('detectEditableSourceIncrementalPatchWithDiagnostics rejects MJCF include edits', () => {
  const previousContent = `<mujoco model="include_demo">
  <include file="shared.xml"/>
  <worldbody>
    <body name="base"><geom type="sphere" size="0.01"/></body>
  </worldbody>
</mujoco>`;
  const nextContent = previousContent.replace('size="0.01"', 'size="0.02"');
  const dirtyStart = nextContent.indexOf('size="0.02"');
  assert.notEqual(dirtyStart, -1);

  const result = detectEditableSourceIncrementalPatchWithDiagnostics({
    file: { name: 'robot.xml', format: 'mjcf' },
    previousContent,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'size="0.02"'.length }],
  });

  assert.equal(result.patch, null);
  assert.equal(result.diagnostics.skipReason, 'mjcf-include');
});

test('applyEditableSourceIncrementalPatch returns null when the current state no longer matches the patch', () => {
  const currentState = parseURDF(URDF_LINK_FIXTURE);
  assert.ok(currentState, 'expected URDF fixture to parse');
  const nextContent = URDF_LINK_FIXTURE.replace('length="0.5"', 'length="1"');
  const dirtyStart = nextContent.indexOf('length="1"');
  assert.notEqual(dirtyStart, -1);

  const patch = detectEditableSourceIncrementalPatch({
    file: { name: 'robot.urdf', format: 'urdf' },
    previousContent: URDF_LINK_FIXTURE,
    nextContent,
    dirtyRanges: [{ startOffset: dirtyStart, endOffset: dirtyStart + 'length="1"'.length }],
  });
  assert.ok(patch);

  delete currentState.links.base_link;

  assert.equal(
    applyEditableSourceIncrementalPatch({
      patch,
      currentState,
    }),
    null,
  );
});

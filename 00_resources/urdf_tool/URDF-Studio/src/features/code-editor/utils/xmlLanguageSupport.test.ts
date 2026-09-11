import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getDocumentLanguageId,
  getXmlCompletionEntries,
  resolveXmlCompletionEntryForContext,
  supportsDocumentValidation,
} from './xmlLanguageSupport.ts';

test('maps Xacro documents to XML language mode for Monaco CDN runtime', () => {
  assert.equal(getDocumentLanguageId('xacro'), 'xml');
  assert.equal(supportsDocumentValidation('xacro'), true);
});

test('returns URDF tags and snippets in URDF tag context', () => {
  const labels = getXmlCompletionEntries('urdf', '<').map((entry) => entry.label);

  assert.ok(labels.includes('robot'));
  assert.ok(!labels.includes('link'));
  assert.ok(!labels.includes('joint-snippet'));
  assert.ok(!labels.includes('xacro:macro'));
});

test('returns URDF joint type values inside joint type attributes', () => {
  const labels = getXmlCompletionEntries('urdf', '<joint type="').map((entry) => entry.label);

  assert.ok(labels.includes('revolute'));
  assert.ok(labels.includes('continuous'));
  assert.ok(labels.includes('fixed'));
});

test('returns Xacro-specific tags and snippets while keeping other flavors isolated', () => {
  const xacroLabels = getXmlCompletionEntries('xacro', '<xacro:').map((entry) => entry.label);
  const mjcfLabels = getXmlCompletionEntries('mjcf', '<').map((entry) => entry.label);

  assert.ok(xacroLabels.includes('xacro:macro'));
  assert.ok(xacroLabels.includes('macro-snippet'));
  assert.ok(mjcfLabels.includes('mujoco'));
  assert.ok(!mjcfLabels.includes('xacro:macro'));
});

test('returns schema-derived URDF tags and attributes beyond the original hardcoded set', () => {
  const tagLabels = getXmlCompletionEntries('urdf', '<robot>\n  <').map((entry) => entry.label);
  const attributeLabels = getXmlCompletionEntries('urdf', '<robot ').map((entry) => entry.label);

  assert.ok(tagLabels.includes('sensor'));
  assert.ok(tagLabels.includes('gazebo'));
  assert.ok(attributeLabels.includes('version'));
});

test('limits URDF child tag suggestions to the active robot parent context', () => {
  const labels = getXmlCompletionEntries('urdf', '<robot>\n  <').map((entry) => entry.label);

  assert.ok(labels.includes('link'));
  assert.ok(labels.includes('joint'));
  assert.ok(labels.includes('joint-snippet'));
  assert.ok(!labels.includes('limit'));
});

test('limits URDF child tag suggestions to the active joint parent context', () => {
  const labels = getXmlCompletionEntries(
    'urdf',
    '<robot name="demo">\n  <joint name="base_joint" type="fixed">\n    <',
  ).map((entry) => entry.label);

  assert.ok(labels.includes('parent'));
  assert.ok(labels.includes('child'));
  assert.ok(labels.includes('limit'));
  assert.ok(!labels.includes('link'));
  assert.ok(!labels.includes('joint-snippet'));
});

test('returns URDF geometry child tags inside geometry scope', () => {
  const labels = getXmlCompletionEntries(
    'urdf',
    '<robot name="demo">\n  <link name="base_link">\n    <visual>\n      <geometry>\n        <',
  ).map((entry) => entry.label);

  assert.ok(labels.includes('box'));
  assert.ok(labels.includes('cylinder'));
  assert.ok(labels.includes('sphere'));
  assert.ok(labels.includes('mesh'));
  assert.ok(!labels.includes('joint'));
});

test('reuses cached completion arrays for repeated contexts to keep suggest cheap', () => {
  const first = getXmlCompletionEntries('urdf', '<robot ');
  const second = getXmlCompletionEntries('urdf', '<robot ');

  assert.equal(first, second);
});

test('reuses cached child-tag arrays for repeated parent contexts', () => {
  const prefix = '<robot name="demo">\n  <joint name="base_joint" type="fixed">\n    <';
  const first = getXmlCompletionEntries('urdf', prefix);
  const second = getXmlCompletionEntries('urdf', prefix);

  assert.equal(first, second);
});

test('expands URDF tag completions into paired-tag snippets in opening tag context', () => {
  const prefix = '<robot name="demo">\n  <joi';
  const jointEntry = getXmlCompletionEntries('urdf', prefix).find(
    (entry) => entry.label === 'joint',
  );
  assert.ok(jointEntry, 'expected "joint" completion entry');

  const resolved = resolveXmlCompletionEntryForContext(jointEntry, prefix);
  assert.equal(resolved.insertText, 'joint${1}>$0</joint>');
  assert.equal(resolved.insertAsSnippet, true);
});

test('keeps closing-tag completions plain in closing tag context', () => {
  const prefix = '<robot name="demo">\n  </joi';
  const jointEntry = getXmlCompletionEntries('urdf', prefix).find(
    (entry) => entry.label === 'joint',
  );
  assert.ok(jointEntry, 'expected "joint" completion entry');

  const resolved = resolveXmlCompletionEntryForContext(jointEntry, prefix);
  assert.equal(resolved.insertText, 'joint');
  assert.equal(resolved.insertAsSnippet, undefined);
});

test('returns SDF semantic tag and enum-value completions', () => {
  const rootLabels = getXmlCompletionEntries('sdf', '<').map((entry) => entry.label);
  const modelChildLabels = getXmlCompletionEntries('sdf', '<sdf version="1.10">\n  <').map(
    (entry) => entry.label,
  );
  const jointTypeLabels = getXmlCompletionEntries('sdf', '<joint type="').map(
    (entry) => entry.label,
  );

  assert.ok(rootLabels.includes('sdf'));
  assert.ok(modelChildLabels.includes('model'));
  assert.ok(modelChildLabels.includes('world'));
  assert.ok(jointTypeLabels.includes('revolute'));
  assert.ok(jointTypeLabels.includes('fixed'));
});

test('returns MJCF semantic tag and enum-value completions', () => {
  const rootLabels = getXmlCompletionEntries('mjcf', '<').map((entry) => entry.label);
  const mujocoChildLabels = getXmlCompletionEntries('mjcf', '<mujoco model="demo">\n  <').map(
    (entry) => entry.label,
  );
  const bodyChildLabels = getXmlCompletionEntries(
    'mjcf',
    '<mujoco model="demo">\n  <worldbody>\n    <body name="base">\n      <',
  ).map((entry) => entry.label);
  const geomTypeLabels = getXmlCompletionEntries('mjcf', '<geom type="').map(
    (entry) => entry.label,
  );

  assert.ok(rootLabels.includes('mujoco'));
  assert.ok(bodyChildLabels.includes('geom'));
  assert.ok(bodyChildLabels.includes('joint'));
  assert.ok(geomTypeLabels.includes('box'));
  assert.ok(geomTypeLabels.includes('mesh'));

  assert.ok(mujocoChildLabels.includes('contact'));
  assert.ok(mujocoChildLabels.includes('sensor'));
  assert.ok(mujocoChildLabels.includes('tendon'));
  assert.ok(mujocoChildLabels.includes('visual'));
  assert.ok(mujocoChildLabels.includes('extension'));
  assert.ok(bodyChildLabels.includes('frame'));
  assert.ok(
    getXmlCompletionEntries('mjcf', '<mujoco model="demo">\n  <worldbody>\n    <frame>\n      <')
      .map((entry) => entry.label)
      .includes('geom'),
  );
});

test('offers compiler attribute completions for extended MJCF compiler options', () => {
  const compilerLabels = getXmlCompletionEntries('mjcf', '<mujoco \n  <compiler ').map(
    (entry) => entry.label,
  );
  assert.ok(compilerLabels.includes('autolimits'));
  assert.ok(compilerLabels.includes('texturedir'));
  assert.ok(compilerLabels.includes('assetdir'));
  assert.ok(compilerLabels.includes('inertiafromgeom'));
  assert.ok(compilerLabels.includes('eulerseq'));
});

test('supplies tendon/actuator/default context completions', () => {
  const defaultLabels = getXmlCompletionEntries(
    'mjcf',
    '<mujoco>\n  <default class="proto">\n    <',
  ).map((entry) => entry.label);
  assert.ok(defaultLabels.includes('position'));
  assert.ok(defaultLabels.includes('general'));

  const actuatorLabels = getXmlCompletionEntries('mjcf', '<mujoco>\n  <actuator>\n    <').map(
    (entry) => entry.label,
  );
  assert.ok(actuatorLabels.includes('damper'));
  assert.ok(actuatorLabels.includes('muscle'));
  assert.ok(actuatorLabels.includes('adhesion'));

  const tendonAttrLabels = getXmlCompletionEntries('mjcf', '<tendon ').map((entry) => entry.label);
  assert.ok(tendonAttrLabels.includes('stiffness'));
  assert.ok(tendonAttrLabels.includes('sidesite'));
});

test('suggests URDF link names for joint parent/child link attribute values', () => {
  const labels = getXmlCompletionEntries(
    'urdf',
    `<robot name="demo">
  <link name="base_link"/>
  <link name="arm_link"/>
  <joint name="joint1" type="revolute">
    <parent link="`,
  ).map((entry) => entry.label);

  assert.ok(labels.includes('base_link'));
  assert.ok(labels.includes('arm_link'));
});

test('suggests Xacro macro tag and macro params in context', () => {
  const macroTagLabels = getXmlCompletionEntries(
    'xacro',
    `<xacro:macro name="wheel_joint" params="parent child radius:=0.1"/>
<robot name="demo">
  <xacro:`,
  ).map((entry) => entry.label);

  const macroParamLabels = getXmlCompletionEntries(
    'xacro',
    `<xacro:macro name="wheel_joint" params="parent child radius:=0.1 *block"/>
<robot name="demo">
  <xacro:wheel_joint `,
  ).map((entry) => entry.label);

  assert.ok(macroTagLabels.includes('xacro:wheel_joint'));
  assert.ok(macroParamLabels.includes('parent'));
  assert.ok(macroParamLabels.includes('child'));
  assert.ok(macroParamLabels.includes('radius'));
  assert.ok(macroParamLabels.includes('block'));
});

test('suggests MJCF joint references and asset names for actuator/geom attributes', () => {
  const jointLabels = getXmlCompletionEntries(
    'mjcf',
    `<mujoco model="demo">
  <worldbody>
    <body name="base">
      <joint name="hip" type="hinge"/>
      <joint name="knee" type="hinge"/>
    </body>
  </worldbody>
  <actuator>
    <motor joint="`,
  ).map((entry) => entry.label);

  const meshLabels = getXmlCompletionEntries(
    'mjcf',
    `<mujoco model="demo">
  <asset>
    <mesh name="upper_mesh" file="upper.stl"/>
    <material name="steel" rgba="0.7 0.7 0.7 1"/>
  </asset>
  <worldbody>
    <body name="base">
      <geom mesh="`,
  ).map((entry) => entry.label);

  const materialLabels = getXmlCompletionEntries(
    'mjcf',
    `<mujoco model="demo">
  <asset>
    <mesh name="upper_mesh" file="upper.stl"/>
    <material name="steel" rgba="0.7 0.7 0.7 1"/>
  </asset>
  <worldbody>
    <body name="base">
      <geom material="`,
  ).map((entry) => entry.label);

  assert.ok(jointLabels.includes('hip'));
  assert.ok(jointLabels.includes('knee'));
  assert.ok(meshLabels.includes('upper_mesh'));
  assert.ok(materialLabels.includes('steel'));
});

test('enables structural validation for URDF/Xacro/SDF/MJCF flavors', () => {
  assert.equal(supportsDocumentValidation('urdf'), true);
  assert.equal(supportsDocumentValidation('xacro'), true);
  assert.equal(supportsDocumentValidation('sdf'), true);
  assert.equal(supportsDocumentValidation('mjcf'), true);
  assert.equal(supportsDocumentValidation('equivalent-mjcf'), true);
  assert.equal(supportsDocumentValidation('usd'), false);
});

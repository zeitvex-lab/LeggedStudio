import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getSourceCodeDocumentFlavor,
  isSourceCodeDocumentReadOnly,
  shouldUseEquivalentMjcfForUsdSource,
} from './sourceCodeDisplay.ts';

test('treats packaged USDZ files as read-only equivalent MJCF sources', () => {
  const file = {
    name: 'robots/unitree/go2.usdz',
    format: 'usd' as const,
    content: '',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), true);
  assert.equal(getSourceCodeDocumentFlavor(file), 'equivalent-mjcf');
});

test('treats empty generic USD files as binary-equivalent MJCF sources', () => {
  const file = {
    name: 'robots/demo/scene.usd',
    format: 'usd' as const,
    content: '',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), true);
  assert.equal(getSourceCodeDocumentFlavor(file), 'equivalent-mjcf');
});

test('treats textual USDA sources as read-only USD source documents', () => {
  const file = {
    name: 'robots/demo/scene.usda',
    format: 'usd' as const,
    content: '#usda 1.0\n(\n    defaultPrim = "Robot"\n)\n',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), false);
  assert.equal(getSourceCodeDocumentFlavor(file), 'usd');
});

test('treats USD and equivalent MJCF source documents as read-only in editor', () => {
  assert.equal(isSourceCodeDocumentReadOnly('usd'), true);
  assert.equal(isSourceCodeDocumentReadOnly('equivalent-mjcf'), true);
  assert.equal(isSourceCodeDocumentReadOnly('urdf'), false);
  assert.equal(isSourceCodeDocumentReadOnly('mjcf'), false);
});

test('keeps explicit MJCF files in MJCF mode', () => {
  const file = {
    name: 'robots/demo/scene.xml',
    format: 'mjcf' as const,
    content: '<mujoco model="demo" />',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), false);
  assert.equal(getSourceCodeDocumentFlavor(file), 'mjcf');
});

test('keeps explicit Xacro files in Xacro mode and editable', () => {
  const file = {
    name: 'robots/demo/arm.urdf.xacro',
    format: 'xacro' as const,
    content: '<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="arm" />',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), false);
  assert.equal(getSourceCodeDocumentFlavor(file), 'xacro');
  assert.equal(isSourceCodeDocumentReadOnly('xacro'), false);
});

test('keeps explicit SDF files in SDF mode and editable', () => {
  const file = {
    name: 'robots/demo/model.sdf',
    format: 'sdf' as const,
    content: '<sdf version="1.7"><model name="demo"><link name="base_link" /></model></sdf>',
  };

  assert.equal(shouldUseEquivalentMjcfForUsdSource(file), false);
  assert.equal(getSourceCodeDocumentFlavor(file), 'sdf');
  assert.equal(isSourceCodeDocumentReadOnly('sdf'), false);
});

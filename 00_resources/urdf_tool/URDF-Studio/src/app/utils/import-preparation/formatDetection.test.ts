import test from 'node:test';
import assert from 'node:assert/strict';

import { ensureWorkerXmlDomApis } from '@/core/utils/ensureWorkerXmlDomApis';

import { detectImportFormat } from './formatDetection.ts';

ensureWorkerXmlDomApis(globalThis as typeof globalThis);

test('detectImportFormat prefers extension-based format matches', () => {
  assert.equal(detectImportFormat('<robot name="demo" />', 'demo.urdf'), 'urdf');
  assert.equal(detectImportFormat('<robot name="demo" />', 'demo.urdf.xacro'), 'xacro');
  assert.equal(detectImportFormat('<sdf version="1.7" />', 'demo.sdf'), 'sdf');
  assert.equal(detectImportFormat('#usda 1.0', 'demo.usdc'), 'usd');
});

test('detectImportFormat falls back to XML content heuristics', () => {
  assert.equal(
    detectImportFormat('<mujoco model="demo"><worldbody /></mujoco>', 'demo.xml'),
    'mjcf',
  );
  assert.equal(
    detectImportFormat('<sdf version="1.7"><model name="demo" /></sdf>', 'demo.xml'),
    'sdf',
  );
  assert.equal(
    detectImportFormat(
      '<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="demo"></robot>',
      'demo.xml',
    ),
    'xacro',
  );
  assert.equal(detectImportFormat('<robot name="demo"></robot>', 'demo.xml'), 'urdf');
});

test('detectImportFormat classifies custom-root MJCF include fragments', () => {
  assert.equal(
    detectImportFormat(
      `<panda>
        <asset>
          <mesh name="body" file="body.stl" />
        </asset>
        <worldbody>
          <body name="base">
            <geom type="mesh" mesh="body" />
          </body>
        </worldbody>
      </panda>`,
      'panda.xml',
    ),
    'mjcf',
  );
});

test('detectImportFormat falls back to content when the filename is unhelpful', () => {
  assert.equal(detectImportFormat('#usda 1.0\ndef Xform "demo" {}', 'payload.txt'), 'usd');
  assert.equal(detectImportFormat('plain text only', 'payload.txt'), null);
});

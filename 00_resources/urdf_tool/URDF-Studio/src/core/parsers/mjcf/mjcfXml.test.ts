import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import { isSourceOnlyMJCFDocument, isStandaloneMJCFDocument } from './mjcfXml.ts';

function installDomParser() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  (globalThis as { DOMParser?: typeof DOMParser }).DOMParser = dom.window.DOMParser;
  return dom;
}

test('isStandaloneMJCFDocument recognizes standalone MJCF entrypoints', () => {
  const dom = installDomParser();
  assert.equal(
    isStandaloneMJCFDocument(`<mujoco model="demo">
  <worldbody>
    <body name="base_link" />
  </worldbody>
</mujoco>`),
    true,
  );
  dom.window.close();
});

test('isStandaloneMJCFDocument rejects mujocoinclude fragments', () => {
  const dom = installDomParser();
  const fragment = `<mujocoinclude>
  <asset>
    <mesh name="part" file="mesh.stl" />
  </asset>
</mujocoinclude>`;

  assert.equal(isSourceOnlyMJCFDocument(fragment), true);
  assert.equal(isStandaloneMJCFDocument(fragment), false);
  dom.window.close();
});

test('isSourceOnlyMJCFDocument accepts custom-root include fragments', () => {
  const dom = installDomParser();
  const fragment = `<panda>
  <asset>
    <mesh name="body" file="body.stl" />
  </asset>
  <worldbody>
    <body name="base">
      <geom type="mesh" mesh="body" />
    </body>
  </worldbody>
</panda>`;

  assert.equal(isSourceOnlyMJCFDocument(fragment), true);
  assert.equal(isStandaloneMJCFDocument(fragment), false);
  dom.window.close();
});

test('isStandaloneMJCFDocument rejects worldbody-free mujoco documents', () => {
  const dom = installDomParser();
  const fragment = `<mujoco model="demo">
  <asset>
    <mesh name="part" file="mesh.stl" />
  </asset>
</mujoco>`;

  assert.equal(isSourceOnlyMJCFDocument(fragment), true);
  assert.equal(isStandaloneMJCFDocument(fragment), false);
  dom.window.close();
});

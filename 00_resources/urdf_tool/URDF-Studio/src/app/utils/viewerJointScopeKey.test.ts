import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveViewerJointScopeKey } from './viewerJointScopeKey.ts';

test('uses preview file scope when previewing another file', () => {
  assert.equal(
    resolveViewerJointScopeKey({
      previewFileName: 'preview/arm.urdf',
      sourceFile: { name: 'selected/robot.urdf' },
      sourceFilePath: 'resolved/robot.urdf',
      robotName: 'shared_robot',
    }),
    'preview:preview/arm.urdf',
  );
});

test('prefers the selected file name over the resolved source path for joint state scope', () => {
  assert.equal(
    resolveViewerJointScopeKey({
      sourceFile: { name: 'test/mujoco_menagerie-main/pal_tiago/tiago_motor.xml' },
      sourceFilePath: 'test/mujoco_menagerie-main/pal_tiago/tiago.xml',
      robotName: 'tiago',
    }),
    'current:test/mujoco_menagerie-main/pal_tiago/tiago_motor.xml',
  );
});

test('falls back to source path and robot name only when no file entry is available', () => {
  assert.equal(
    resolveViewerJointScopeKey({
      sourceFilePath: 'resolved/robot.urdf',
      robotName: 'shared_robot',
    }),
    'current:resolved/robot.urdf',
  );

  assert.equal(
    resolveViewerJointScopeKey({
      robotName: 'shared_robot',
    }),
    'current:shared_robot',
  );
});

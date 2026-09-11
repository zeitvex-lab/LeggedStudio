import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotFile } from '@/types';
import { pickFastPreparedPreferredFile } from './fastPreferredFile.ts';

function createRobotFile(name: string, format: RobotFile['format'], content = ''): RobotFile {
  return {
    name,
    format,
    content,
  };
}

test('pickFastPreparedPreferredFile avoids heavyweight mixed-format selectors for large bundles', () => {
  const files: RobotFile[] = [
    createRobotFile(
      'robots/demo/demo.urdf',
      'urdf',
      '<robot name="demo"><link name="base_link" /></robot>',
    ),
    createRobotFile(
      'robots/demo/demo.xml',
      'mjcf',
      '<mujoco model="demo"><worldbody><body name="base_link" /></worldbody></mujoco>',
    ),
    ...Array.from({ length: 640 }, (_, index) =>
      createRobotFile(`robots/demo/meshes/part_${index}.stl`, 'mesh'),
    ),
  ];
  const filePool = [...files];

  Object.defineProperty(filePool, 'filter', {
    configurable: true,
    value: () => {
      throw new Error('heavy selector should not inspect the full file pool in fast mode');
    },
  });
  const preferred = pickFastPreparedPreferredFile(files, filePool);

  assert.ok(preferred);
  assert.notEqual(preferred?.format, 'mesh');
});

test('pickFastPreparedPreferredFile keeps broad Unitree USDA imports on canonical roots', () => {
  const files: RobotFile[] = [
    createRobotFile('g1_description/g1_23dof_mode_10.usda', 'usd'),
    createRobotFile('g1_description/g1_23dof.usda', 'usd'),
    createRobotFile('g1_description/g1_29dof_with_hand.usda', 'usd'),
    createRobotFile('g1_description/g1_29dof_lock_waist.usda', 'usd'),
    createRobotFile('g1_description/configuration/g1_23dof_base.usda', 'usd'),
    ...Array.from({ length: 640 }, (_, index) =>
      createRobotFile(`g1_description/meshes/part_${index}.obj`, 'mesh'),
    ),
  ];

  const preferred = pickFastPreparedPreferredFile(files, files);

  assert.equal(preferred?.name, 'g1_description/g1_23dof.usda');
});

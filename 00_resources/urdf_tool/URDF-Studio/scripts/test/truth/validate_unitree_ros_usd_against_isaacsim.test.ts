import assert from 'node:assert/strict';
import fsPromises from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { discoverFixtures } from './validate_unitree_ros_usd_against_isaacsim.ts';

test('discoverFixtures includes URDF and MJCF XML sources and reports non-robot XML skips', async () => {
  const tempRoot = await fsPromises.mkdtemp(path.join(os.tmpdir(), 'unitree-isaac-discovery-'));
  const fixtureRoot = path.join(tempRoot, 'robots');
  const robotRoot = path.join(fixtureRoot, 'go2_description');
  const urdfDir = path.join(robotRoot, 'urdf');
  const mjcfDir = path.join(robotRoot, 'mjcf');

  await fsPromises.mkdir(urdfDir, { recursive: true });
  await fsPromises.mkdir(mjcfDir, { recursive: true });
  await fsPromises.writeFile(
    path.join(robotRoot, 'package.xml'),
    '<package><name>go2_description</name></package>',
    'utf8',
  );
  await fsPromises.writeFile(
    path.join(urdfDir, 'go2.urdf'),
    '<robot name="go2"><link name="base"/></robot>',
    'utf8',
  );
  await fsPromises.writeFile(
    path.join(mjcfDir, 'go2.xml'),
    '<mujoco model="go2"><worldbody><body name="base"/></worldbody></mujoco>',
    'utf8',
  );

  const result = await discoverFixtures({
    artifactsDir: path.join(tempRoot, 'artifacts'),
    compressMeshes: false,
    fixtureRoot,
    isaacLabRoot: tempRoot,
    isaacPython: process.execPath,
    limit: null,
    meshQuality: 100,
    modelFilters: [],
    outputPath: path.join(tempRoot, 'summary.json'),
  });

  assert.deepEqual(
    result.fixtures.map((fixture) => ({
      sourceFormat: fixture.sourceFormat,
      sourcePath: fixture.entryPath,
    })),
    [
      { sourceFormat: 'mjcf', sourcePath: 'go2_description/mjcf/go2.xml' },
      { sourceFormat: 'urdf', sourcePath: 'go2_description/urdf/go2.urdf' },
    ],
  );
  assert.deepEqual(result.skipped, [
    {
      entryPath: 'go2_description/package.xml',
      message: null,
      status: 'unsupported_format',
    },
  ]);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';

import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { JointType, type RobotFile } from '@/types';
import { autoSeedAssembly } from './auto_seed_assembly';

const { window } = new JSDOM();

if (!globalThis.DOMParser) {
  globalThis.DOMParser = window.DOMParser;
}

if (!globalThis.XMLSerializer) {
  globalThis.XMLSerializer = window.XMLSerializer as typeof XMLSerializer;
}

function readFixture(path: string): string {
  return fs.readFileSync(path, 'utf8');
}

function createMjcfFile(name: string, content: string): RobotFile {
  return {
    name,
    format: 'mjcf',
    content,
  };
}

test('autoSeedAssembly keeps single selected-file link and joint names unmodified', () => {
  const file = createMjcfFile(
    'test/mujoco_menagerie-main/booster_t1/t1.xml',
    `<mujoco model="T1">
      <worldbody>
        <body name="Trunk" pos="0 0 0.7">
          <freejoint/>
          <body name="H1" pos="0 0 0.2">
            <joint name="AAHead_yaw" axis="0 0 1" range="-1 1"/>
            <geom type="sphere" size="0.05"/>
          </body>
        </body>
      </worldbody>
    </mujoco>`,
  );
  const importResult = resolveRobotFileData(file, {
    availableFiles: [file],
    allFileContents: { [file.name]: file.content },
    assets: {},
  });

  assert.equal(importResult.status, 'ready');
  if (importResult.status !== 'ready') {
    assert.fail('expected MJCF fixture to resolve');
  }

  const assembly = autoSeedAssembly(importResult.robotData, file.name, {
    sourceFile: file,
    availableFiles: [file],
    allFileContents: { [file.name]: file.content },
    assets: {},
  });
  const [component] = Object.values(assembly.components);

  assert.ok(component);
  assert.deepEqual(assembly.transform, {
    position: { x: 0, y: 0, z: 0 },
    rotation: { r: 0, p: 0, y: 0 },
  });
  assert.deepEqual(component.transform, assembly.transform);
  assert.equal(component.visible, true);
  assert.equal(component.robot.rootLinkId, 'world');
  assert.equal(component.robot.links.Trunk?.name, 'Trunk');
  assert.equal(component.robot.links.H1?.name, 'H1');
  assert.equal(component.robot.joints.joint_0?.name, 'joint_0');
  assert.equal(component.robot.joints.AAHead_yaw?.name, 'AAHead_yaw');
  assert.equal(component.robot.links.t1_Trunk, undefined);
  assert.equal(component.robot.joints.t1_AAHead_yaw, undefined);
});

test('autoSeedAssembly can explicitly split MJCF scene wrappers into scene and robot components with a bridge', () => {
  const sceneFile = createMjcfFile(
    'test/mujoco_menagerie-main/unitree_go2/scene.xml',
    readFixture('test/mujoco_menagerie-main/unitree_go2/scene.xml'),
  );
  const robotFile = createMjcfFile(
    'test/mujoco_menagerie-main/unitree_go2/go2.xml',
    readFixture('test/mujoco_menagerie-main/unitree_go2/go2.xml'),
  );
  const availableFiles = [sceneFile, robotFile];
  const allFileContents = Object.fromEntries(
    availableFiles.map((file) => [file.name, file.content]),
  );
  const importResult = resolveRobotFileData(sceneFile, {
    availableFiles,
    allFileContents,
    assets: {},
  });

  assert.equal(importResult.status, 'ready');
  if (importResult.status !== 'ready') {
    assert.fail('expected scene fixture to resolve');
  }

  const assembly = autoSeedAssembly(importResult.robotData, sceneFile.name, {
    sourceFile: sceneFile,
    availableFiles,
    allFileContents,
    assets: {},
    splitMjcfSceneIncludes: true,
  });
  const components = Object.values(assembly.components);
  const bridges = Object.values(assembly.bridges);

  assert.equal(assembly.name, 'go2');
  assert.deepEqual(
    components
      .map((component) => component.sourceFile)
      .filter((sourceFile): sourceFile is string => Boolean(sourceFile))
      .sort((left, right) => left.localeCompare(right)),
    [robotFile.name, sceneFile.name].sort((left, right) => left.localeCompare(right)),
  );
  assert.equal(
    components.find((component) => component.sourceFile === robotFile.name)?.name,
    'go2',
  );
  assert.equal(bridges.length, 1);
  assert.equal(bridges[0]?.joint.type, JointType.FIXED);
  assert.equal(
    bridges[0]?.parentComponentId,
    components.find((component) => component.sourceFile === sceneFile.name)?.id,
  );
  assert.equal(
    bridges[0]?.childComponentId,
    components.find((component) => component.sourceFile === robotFile.name)?.id,
  );
  components.forEach((component) => {
    assert.equal(component.visible, true);
    assert.deepEqual(component.transform, {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    });
    assert.equal(
      Object.keys(component.robot.links).some((linkId) => linkId.startsWith(`${component.id}_`)),
      false,
    );
  });
});

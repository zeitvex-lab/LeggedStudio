import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { JSDOM } from 'jsdom';

import { resolveRobotFileData } from '@/core/parsers/importRobotFile';
import { generateSDF } from '@/core/parsers/sdf/sdfGenerator';
import { generateURDF } from '@/core/parsers/urdf/urdfGenerator';
import { parseURDF } from '@/core/parsers/urdf/parser';
import type { RobotFile, RobotState } from '@/types';
import { exportRobotToUsd } from './usdExport';

const dom = new JSDOM('<!doctype html><html><body></body></html>');
globalThis.DOMParser = dom.window.DOMParser as typeof DOMParser;
globalThis.XMLSerializer = dom.window.XMLSerializer as typeof XMLSerializer;
globalThis.ProgressEvent = dom.window.ProgressEvent as typeof ProgressEvent;

function createExportableSdfFile(): RobotFile {
  return {
    name: 'robots/demo/model.sdf',
    format: 'sdf' as RobotFile['format'],
    content: `<?xml version="1.0"?>
<sdf version="1.7">
  <model name="demo_sdf_export">
    <link name="base_link">
      <visual name="body">
        <geometry>
          <box>
            <size>1 2 3</size>
          </box>
        </geometry>
      </visual>
      <collision name="body_collision">
        <geometry>
          <box>
            <size>1 2 3</size>
          </box>
        </geometry>
      </collision>
      <inertial>
        <mass>2.5</mass>
        <inertia>
          <ixx>1</ixx><ixy>0</ixy><ixz>0</ixz><iyy>2</iyy><iyz>0</iyz><izz>3</izz>
        </inertia>
      </inertial>
    </link>
    <link name="tip_link">
      <pose>0 0 1 0 0 0</pose>
      <visual name="tip_visual">
        <geometry>
          <cylinder>
            <radius>0.1</radius>
            <length>0.4</length>
          </cylinder>
        </geometry>
      </visual>
    </link>
    <joint name="tip_joint" type="revolute">
      <parent>base_link</parent>
      <child>tip_link</child>
      <axis>
        <xyz>0 0 1</xyz>
        <limit>
          <lower>-1.57</lower>
          <upper>1.57</upper>
          <effort>10</effort>
          <velocity>2</velocity>
        </limit>
      </axis>
    </joint>
  </model>
</sdf>`,
  };
}

function createAlohaMjcfContext(): {
  allFileContents: Record<string, string>;
  availableFiles: RobotFile[];
  sourceFile: RobotFile;
} {
  const fixtureRoot = path.resolve('test/mujoco_menagerie-main/aloha');
  const allFileContents: Record<string, string> = {};
  const availableFiles: RobotFile[] = [];

  fs.readdirSync(fixtureRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.xml'))
    .forEach((entry) => {
      const filePath = path.join(fixtureRoot, entry.name).replace(/\\/g, '/');
      const content = fs.readFileSync(filePath, 'utf8');
      const file: RobotFile = {
        name: filePath,
        format: 'mjcf' as RobotFile['format'],
        content,
      };
      allFileContents[filePath] = content;
      availableFiles.push(file);
    });

  const sourcePath = path.join(fixtureRoot, 'aloha.xml').replace(/\\/g, '/');
  const sourceFile = availableFiles.find((file) => file.name === sourcePath);
  assert.ok(sourceFile, 'expected Aloha MJCF fixture to be available');

  return {
    allFileContents,
    availableFiles,
    sourceFile,
  };
}

function toRobotState(robotData: ReturnType<typeof resolveRobotFileData> extends infer TResult
  ? TResult extends { status: 'ready'; robotData: infer TData }
    ? TData
    : never
  : never): RobotState {
  return {
    ...robotData,
    selection: { type: null, id: null },
  };
}

test('SDF imports can export to URDF and USD archives', async () => {
  const importResult = resolveRobotFileData(createExportableSdfFile());

  assert.equal(importResult.status, 'ready');
  if (importResult.status !== 'ready') {
    assert.fail('expected SDF import result to be ready');
  }

  const robot = toRobotState(importResult.robotData);
  const urdfContent = generateURDF(robot);
  const urdfRoundtrip = parseURDF(urdfContent);

  assert.ok(urdfRoundtrip, 'expected generated URDF to parse back');
  assert.equal(urdfRoundtrip.name, 'demo_sdf_export');
  assert.match(urdfContent, /<link name="base_link">/);
  assert.match(urdfContent, /<joint name="tip_joint" type="revolute">/);

  const usdPayload = await exportRobotToUsd({
    robot,
    exportName: robot.name,
    assets: {},
  });

  assert.equal(usdPayload.downloadFileName, 'demo_sdf_export.usd');
  assert.equal(usdPayload.archiveFileName, 'demo_sdf_export_usd.zip');
  assert.deepEqual(
    [...usdPayload.archiveFiles.keys()].sort(),
    [
      'demo_sdf_export/usd/configuration/demo_sdf_export_description_base.usd',
      'demo_sdf_export/usd/configuration/demo_sdf_export_description_physics.usd',
      'demo_sdf_export/usd/configuration/demo_sdf_export_description_sensor.usd',
      'demo_sdf_export/usd/demo_sdf_export.usd',
    ],
  );
});

test('Aloha MJCF export to SDF preserves visual material and mesh scale on re-import', () => {
  const { allFileContents, availableFiles, sourceFile } = createAlohaMjcfContext();
  const importResult = resolveRobotFileData(sourceFile, {
    allFileContents,
    availableFiles,
  });

  assert.equal(importResult.status, 'ready');
  if (importResult.status !== 'ready') {
    assert.fail('expected Aloha MJCF import result to be ready');
  }

  const robot = toRobotState(importResult.robotData);
  const sdfContent = generateSDF(robot, { packageName: 'aloha' });

  assert.match(sdfContent, /<diffuse>0\.15000000 0\.15000000 0\.15000000 1\.00000000<\/diffuse>/);
  assert.match(sdfContent, /<scale>0\.001 0\.001 0\.001<\/scale>/);

  const roundTrip = resolveRobotFileData({
    name: 'aloha/model.sdf',
    format: 'sdf' as RobotFile['format'],
    content: sdfContent,
  });

  assert.equal(roundTrip.status, 'ready');
  if (roundTrip.status !== 'ready') {
    assert.fail('expected Aloha SDF re-import result to be ready');
  }

  const baseLink = roundTrip.robotData.links['left/base_link'];
  assert.ok(baseLink, 'expected left/base_link to survive SDF round-trip');
  assert.equal(baseLink.visual.color, '#262626');
  assert.deepEqual(roundTrip.robotData.materials?.['left/base_link'], {
    color: '#262626',
    colorRgba: [0.15, 0.15, 0.15, 1],
  });
  assert.deepEqual(baseLink.visual.dimensions, { x: 0.001, y: 0.001, z: 0.001 });
});

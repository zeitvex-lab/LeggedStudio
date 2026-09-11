import assert from 'node:assert/strict';
import test from 'node:test';

import type { RobotFile } from '@/types';

import { buildSimpleModeDraftFile } from './simpleModeDrafts.ts';

function createRobotFile(
  name: string,
  format: RobotFile['format'],
  content = '<robot name="demo"><link name="base_link" /></robot>',
): RobotFile {
  return {
    name,
    format,
    content,
  };
}

test('buildSimpleModeDraftFile keeps editable URDF drafts beside the source file', () => {
  const selectedFile = createRobotFile(
    'robots/demo/urdf/demo.urdf',
    'urdf',
    '<robot name="edited"><link name="base_link" /></robot>',
  );

  const draftFile = buildSimpleModeDraftFile({
    selectedFile,
    currentSourceContent: selectedFile.content,
    fallbackUrdfContent: '<robot name="fallback" />',
    availableFiles: [],
    now: new Date('2026-04-26T09:45:12Z'),
  });

  assert.deepEqual(draftFile, {
    name: 'robots/demo/urdf/demo.draft-20260426-094512.urdf',
    format: 'urdf',
    content: '<robot name="edited"><link name="base_link" /></robot>',
  });
});

test('buildSimpleModeDraftFile falls back to URDF snapshots and avoids name collisions', () => {
  const selectedFile = createRobotFile(
    'robots/demo/urdf/demo.xacro',
    'xacro',
    '<xacro:robot name="demo" />',
  );

  const draftFile = buildSimpleModeDraftFile({
    selectedFile,
    currentSourceContent: selectedFile.content,
    fallbackUrdfContent: '<robot name="draft"><link name="base_link" /></robot>',
    availableFiles: [createRobotFile('robots/demo/urdf/demo.draft-20260426-094512.urdf', 'urdf')],
    now: new Date('2026-04-26T09:45:12Z'),
  });

  assert.deepEqual(draftFile, {
    name: 'robots/demo/urdf/demo.draft-20260426-094512-2.urdf',
    format: 'urdf',
    content: '<robot name="draft"><link name="base_link" /></robot>',
  });
});

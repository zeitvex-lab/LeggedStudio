import test from 'node:test';
import assert from 'node:assert/strict';

import { getDroppedFiles, getDroppedFilesFromEntries } from './fileTraverser.ts';

type FakeEntry = FileSystemEntry & {
  children?: FakeEntry[];
  fileObject?: File;
};

function createFileEntry(name: string, content: BlobPart = ''): FakeEntry {
  const fileObject = new File([content], name);
  return {
    name,
    fullPath: `/${name}`,
    filesystem: {} as FileSystem,
    isFile: true,
    isDirectory: false,
    file(successCallback: (file: File) => void) {
      successCallback(fileObject);
    },
  } as unknown as FakeEntry;
}

function createDirectoryEntry(name: string, children: FakeEntry[]): FakeEntry {
  return {
    name,
    fullPath: `/${name}`,
    filesystem: {} as FileSystem,
    isFile: false,
    isDirectory: true,
    children,
    createReader() {
      let hasRead = false;
      return {
        readEntries(successCallback: (entries: FileSystemEntry[]) => void) {
          if (hasRead) {
            successCallback([]);
            return;
          }

          hasRead = true;
          successCallback(children);
        },
      };
    },
  } as unknown as FakeEntry;
}

function createDroppedItems(entries: FakeEntry[]): DataTransferItemList {
  return entries.map((entry) => ({
    kind: 'file',
    webkitGetAsEntry: () => entry,
  })) as unknown as DataTransferItemList;
}

test('getDroppedFiles materializes only import candidates from dropped folders', async () => {
  const root = createDirectoryEntry('unitree_ros', [
    createDirectoryEntry('.git', [
      createDirectoryEntry('objects', [createFileEntry('pack.bin', new Uint8Array(10))]),
    ]),
    createFileEntry('README.md', '# Unitree ROS'),
    createFileEntry('CMakeLists.txt', 'cmake_minimum_required(VERSION 3.16)'),
    createFileEntry('package.xml', '<package><name>demo</name></package>'),
    createDirectoryEntry('src', [createFileEntry('controller.cpp', 'int main() { return 0; }')]),
    createDirectoryEntry('robots', [
      createDirectoryEntry('demo_description', [
        createDirectoryEntry('urdf', [createFileEntry('demo.urdf', '<robot name="demo" />')]),
        createDirectoryEntry('meshes', [createFileEntry('base.stl', 'solid demo')]),
      ]),
    ]),
    createDirectoryEntry('motor library', [
      createDirectoryEntry('Acme', [
        createFileEntry('M1.txt', '{"name":"M1","armature":0.01,"velocity":10,"effort":5}'),
      ]),
    ]),
  ]);

  const files = await getDroppedFiles(createDroppedItems([root]));

  assert.deepEqual(
    files.map((file) => file.webkitRelativePath).sort(),
    [
      'unitree_ros/motor library/Acme/M1.txt',
      'unitree_ros/robots/demo_description/meshes/base.stl',
      'unitree_ros/robots/demo_description/urdf/demo.urdf',
    ],
  );
});

test('getDroppedFilesFromEntries processes entries captured before the lazy traverser loads', async () => {
  const root = createDirectoryEntry('lazy_root', [
    createFileEntry('README.md', '# ignored'),
    createDirectoryEntry('robot', [
      createDirectoryEntry('urdf', [createFileEntry('demo.urdf', '<robot name="demo" />')]),
      createDirectoryEntry('meshes', [createFileEntry('base.stl', 'solid demo')]),
    ]),
  ]);

  const files = await getDroppedFilesFromEntries([root]);

  assert.deepEqual(
    files.map((file) => file.webkitRelativePath).sort(),
    ['lazy_root/robot/meshes/base.stl', 'lazy_root/robot/urdf/demo.urdf'],
  );
});

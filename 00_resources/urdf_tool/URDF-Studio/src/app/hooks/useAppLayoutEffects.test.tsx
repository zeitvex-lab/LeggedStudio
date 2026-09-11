import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { useAppLayoutEffects } from './useAppLayoutEffects.ts';
import { createDefaultWorkspace } from '@/core/robot';

type FakeEntry = FileSystemEntry & {
  children?: FakeEntry[];
  fileObject?: File;
};

function restoreGlobalProperty<T extends keyof typeof globalThis>(
  key: T,
  originalValue: (typeof globalThis)[T] | undefined,
) {
  if (originalValue === undefined) {
    delete globalThis[key];
    return;
  }

  Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value: originalValue,
  });
}

function installDomEnvironment() {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;
  const originalNavigator = globalThis.navigator;
  const originalHTMLElement = globalThis.HTMLElement;
  const originalSVGElement = globalThis.SVGElement;
  const originalNode = globalThis.Node;
  const originalLocalStorage = globalThis.localStorage;

  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'http://localhost/',
  });

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    writable: true,
    value: dom.window,
  });
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    writable: true,
    value: dom.window.document,
  });
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    writable: true,
    value: dom.window.navigator,
  });
  Object.defineProperty(globalThis, 'HTMLElement', {
    configurable: true,
    writable: true,
    value: dom.window.HTMLElement,
  });
  Object.defineProperty(globalThis, 'SVGElement', {
    configurable: true,
    writable: true,
    value: dom.window.SVGElement,
  });
  Object.defineProperty(globalThis, 'Node', {
    configurable: true,
    writable: true,
    value: dom.window.Node,
  });
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: dom.window.localStorage,
  });

  return {
    dom,
    restore() {
      dom.window.close();
      restoreGlobalProperty('window', originalWindow);
      restoreGlobalProperty('document', originalDocument);
      restoreGlobalProperty('navigator', originalNavigator);
      restoreGlobalProperty('HTMLElement', originalHTMLElement);
      restoreGlobalProperty('SVGElement', originalSVGElement);
      restoreGlobalProperty('Node', originalNode);
      restoreGlobalProperty('localStorage', originalLocalStorage);
    },
  };
}

function createFileEntry(name: string, content: BlobPart = ''): FakeEntry {
  const fileObject = new File([content], name);
  const entry = {
    name,
    fullPath: `/${name}`,
    filesystem: {} as FileSystem,
    isFile: true,
    isDirectory: false,
    file(successCallback: (file: File) => void) {
      successCallback(fileObject);
    },
  };
  return entry as unknown as FakeEntry;
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

function createInvalidatingDroppedItems(root: FileSystemEntry, isLive: () => boolean) {
  let readCount = 0;
  const item = {
    kind: 'file',
    webkitGetAsEntry: () => {
      readCount += 1;
      return isLive() ? root : null;
    },
  };

  return {
    items: {
      length: 1,
      0: item,
    } as unknown as DataTransferItemList,
    getReadCount: () => readCount,
  };
}

function renderProbe(options: {
  onFileDrop: (files: File[]) => void;
  onDropError?: () => void;
}) {
  const container = document.createElement('div');
  document.body.appendChild(container);

  function Probe() {
    const layoutEffects = useAppLayoutEffects({
      workspace: createDefaultWorkspace('drop-test'),
      selection: null,
      clearSelection: () => {},
      onFileDrop: options.onFileDrop,
      onDropError: options.onDropError ?? (() => {}),
    });

    return React.createElement('div', {
      id: 'drop-target',
      onDrop: layoutEffects.handleDrop,
    });
  }

  const root = createRoot(container);
  flushSync(() => {
    root.render(React.createElement(Probe));
  });

  const target = document.getElementById('drop-target');
  assert.ok(target, 'expected drop target');

  return {
    target,
    cleanup() {
      flushSync(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

async function waitForCondition(condition: () => boolean) {
  const start = Date.now();
  while (Date.now() - start < 5000) {
    if (condition()) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 10));
  }

  assert.fail('timed out waiting for condition');
}

test('drop handler captures folder entries before the lazy traverser import resolves', async () => {
  const domEnvironment = installDomEnvironment();
  const droppedFiles: File[] = [];
  const rootEntry = createDirectoryEntry('lazy_root', [
    createDirectoryEntry('robot', [
      createDirectoryEntry('urdf', [createFileEntry('demo.urdf', '<robot name="demo" />')]),
      createDirectoryEntry('meshes', [createFileEntry('base.stl', 'solid demo')]),
    ]),
  ]);
  let entryIsLive = true;
  const droppedItems = createInvalidatingDroppedItems(rootEntry, () => entryIsLive);
  const rendered = renderProbe({
    onFileDrop: (files) => {
      droppedFiles.push(...files);
    },
  });

  try {
    const event = new domEnvironment.dom.window.Event('drop', {
      bubbles: true,
      cancelable: true,
    });
    Object.defineProperty(event, 'dataTransfer', {
      configurable: true,
      value: {
        types: ['Files'],
        items: droppedItems.items,
      },
    });

    rendered.target.dispatchEvent(event);
    entryIsLive = false;

    await waitForCondition(() => droppedFiles.length === 2);

    assert.equal(droppedItems.getReadCount(), 1);
    assert.deepEqual(
      droppedFiles.map((file) => file.webkitRelativePath).sort(),
      ['lazy_root/robot/meshes/base.stl', 'lazy_root/robot/urdf/demo.urdf'],
    );
  } finally {
    rendered.cleanup();
    await new Promise((resolve) => setTimeout(resolve, 20));
    domEnvironment.restore();
  }
});

import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF } from '@/app/hooks/workspace-source-sync/mjcfViewerRuntimePolicy';
import type { DocumentLoadState } from '@/store/assetsStore';
import { DEFAULT_LINK, JointType, GeometryType } from '@/types';
import type { RobotFile, RobotState } from '@/types';

import { FilePreviewWindow } from './FilePreviewWindow.tsx';
import {
  buildFilePreviewJointMotionState,
  resolveFilePreviewShowVisual,
} from './FilePreviewWindow.tsx';
import { resolveFilePreviewViewerConfig } from './FilePreviewWindow.tsx';
import { resolveFilePreviewViewerSourceFile } from './FilePreviewWindow.tsx';

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
  (globalThis as { SVGElement?: typeof SVGElement }).SVGElement = dom.window.SVGElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { KeyboardEvent?: typeof KeyboardEvent }).KeyboardEvent = dom.window.KeyboardEvent;
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

function createImageFile(name: string): RobotFile {
  return {
    name,
    format: 'mesh',
    content: '',
  };
}

function createRobotFile(name: string): RobotFile {
  return {
    name,
    format: 'urdf',
    content: '<robot name="demo"><link name="base_link" /></robot>',
  };
}

function createMjcfFile(name: string): RobotFile {
  return {
    name,
    format: 'mjcf',
    content: '<mujoco model="demo"><worldbody><body name="base_link" /></worldbody></mujoco>',
  };
}

function createUsdFile(name: string): RobotFile {
  return {
    name,
    format: 'usd',
    content: '#usda 1.0',
  };
}

function createRobotState(name: string): RobotState {
  return {
    name,
    links: {
      base_link: {
        ...structuredClone(DEFAULT_LINK),
        id: 'base_link',
        name: 'base_link',
      },
    },
    joints: {},
    rootLinkId: 'base_link',
    selection: { type: null, id: null },
  };
}

function renderWindow(options: {
  root: Root;
  file: RobotFile | null;
  previewRobot?: RobotState | null;
  previewState?: { urdfContent: string; fileName: string };
  assets?: Record<string, string>;
  documentLoadState?: DocumentLoadState;
  onClose?: () => void;
}) {
  const documentLoadState: DocumentLoadState = options.documentLoadState ?? {
    status: 'ready',
    fileName: options.file?.name ?? null,
    format: options.file?.format ?? null,
    error: null,
  };

  return act(async () => {
    options.root.render(
      <FilePreviewWindow
        file={options.file}
        previewRobot={options.previewRobot ?? null}
        previewState={options.previewState}
        assets={options.assets ?? {}}
        allFileContents={{}}
        availableFiles={options.file ? [options.file] : []}
        documentLoadState={documentLoadState}
        lang="en"
        theme="light"
        showVisual={true}
        onClose={options.onClose ?? (() => {})}
      />,
    );
  });
}

test('resolveFilePreviewViewerSourceFile routes USD previews through RobotState source', () => {
  const usdFile = createUsdFile('robots/demo/demo.usda');

  assert.deepEqual(resolveFilePreviewViewerSourceFile(usdFile), {
    ...usdFile,
    content: USD_ROBOT_STATE_VIEWER_PLACEHOLDER_URDF,
    format: 'urdf',
  });
});

test('resolveFilePreviewViewerConfig reuses standalone MJCF viewer settings', () => {
  const mjcfFile = createMjcfFile('robots/demo/scene.xml');

  assert.deepEqual(resolveFilePreviewViewerConfig(mjcfFile, { showVisual: false }), {
    showVisual: false,
    sourceFile: mjcfFile,
    sourceFilePath: mjcfFile.name,
    viewerSourceFormat: 'mjcf',
  });
});

test('resolveFilePreviewShowVisual derives visibility from the preview robot when no stored preference exists', () => {
  const previewRobot = createRobotState('cassie');
  previewRobot.links.base_link = {
    id: 'base_link',
    name: 'base_link',
    visible: true,
    visual: {
      type: GeometryType.BOX,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#808080',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    collision: {
      type: GeometryType.NONE,
      dimensions: { x: 0, y: 0, z: 0 },
      color: '#ef4444',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
  };

  assert.equal(
    resolveFilePreviewShowVisual({
      previewRobot,
      fallbackShowVisual: false,
      storedPreference: null,
    }),
    true,
  );
  assert.equal(
    resolveFilePreviewShowVisual({
      previewRobot,
      fallbackShowVisual: true,
      storedPreference: false,
    }),
    false,
  );
  assert.equal(
    resolveFilePreviewShowVisual({
      previewRobot: null,
      fallbackShowVisual: false,
      storedPreference: null,
    }),
    false,
  );
});

test('buildFilePreviewJointMotionState forwards MJCF angle and quaternion pose state', () => {
  const previewRobot = createRobotState('cassie');
  previewRobot.joints = {
    knee: {
      id: 'knee',
      name: 'left-knee',
      type: JointType.REVOLUTE,
      parentLinkId: 'base_link',
      childLinkId: 'shin',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      dynamics: { damping: 0, friction: 0 },
      hardware: {
        motorType: 'None',
        motorId: '',
        motorDirection: 1,
        armature: 0,
      },
      angle: -1.1997,
    },
    achilles: {
      id: 'achilles',
      name: 'right-achilles-rod',
      type: JointType.BALL,
      parentLinkId: 'hip',
      childLinkId: 'rod',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      dynamics: { damping: 0, friction: 0 },
      hardware: {
        motorType: 'None',
        motorId: '',
        motorDirection: 1,
        armature: 0,
      },
      quaternion: { x: 0, y: -0.014423187695796426, z: 0, w: 0.9786415639566073 },
    },
  };

  assert.deepEqual(buildFilePreviewJointMotionState(previewRobot), {
    knee: { angle: -1.1997 },
    achilles: {
      quaternion: { x: 0, y: -0.014423187695796426, z: 0, w: 0.9786415639566073 },
    },
  });
  assert.equal(buildFilePreviewJointMotionState(null), undefined);
});

test('FilePreviewWindow does not render stale robot preview content after switching files', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);

  const previousFile = createRobotFile('robots/previous.urdf');
  const nextFile = createRobotFile('robots/next.urdf');

  try {
    await renderWindow({
      root,
      file: nextFile,
      previewRobot: createRobotState('previous'),
      previewState: {
        urdfContent: previousFile.content,
        fileName: previousFile.name,
      },
      documentLoadState: {
        status: 'ready',
        fileName: nextFile.name,
        format: nextFile.format,
        error: null,
      },
    });

    assert.equal(container.textContent?.includes('File Preview: next.urdf'), true);
    assert.equal(
      container.textContent?.includes('Loading robot...'),
      false,
      'stale preview content should not mount the 3D viewer for the next file',
    );
    assert.equal(container.textContent?.includes('No preview image available'), true);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('FilePreviewWindow renders image previews in a floating window and closes from the header control', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);

  const imageFile = createImageFile('textures/poster.png');
  let closeCount = 0;

  try {
    await renderWindow({
      root,
      file: imageFile,
      assets: {
        'textures/poster.png': 'blob:image-preview',
      },
      onClose: () => {
        closeCount += 1;
      },
    });

    assert.equal(container.textContent?.includes('File Preview: poster.png'), true);

    const image = container.querySelector('img');
    assert.ok(image, 'expected the preview window to render an image preview');
    assert.equal(image.getAttribute('src'), 'blob:image-preview');

    const closeButton = container.querySelector('button[aria-label="Close Preview"]');
    assert.ok(closeButton, 'expected a close button in the preview window header');

    await act(async () => {
      closeButton.dispatchEvent(
        new dom.window.MouseEvent('click', {
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    assert.equal(closeCount, 1);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('FilePreviewWindow shows a loading state while preview content is still resolving', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);

  const robotFile = createRobotFile('robots/demo.urdf');

  try {
    await renderWindow({
      root,
      file: robotFile,
      documentLoadState: {
        status: 'loading',
        fileName: robotFile.name,
        format: robotFile.format,
        error: null,
      },
    });

    assert.equal(container.textContent?.includes('Loading robot...'), true);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

test('FilePreviewWindow exposes an add action for addable preview files', async () => {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');
  const root = createRoot(container);

  const robotFile = createRobotFile('robots/demo.urdf');
  const addedFiles: string[] = [];

  try {
    await act(async () => {
      root.render(
        <FilePreviewWindow
          file={robotFile}
          previewRobot={null}
          previewState={undefined}
          assets={{}}
          allFileContents={{}}
          availableFiles={[robotFile]}
          documentLoadState={{
            status: 'ready',
            fileName: robotFile.name,
            format: robotFile.format,
            error: null,
          }}
          lang="en"
          theme="light"
          showVisual={true}
          onClose={() => {}}
          onAddComponent={(file) => {
            addedFiles.push(file.name);
          }}
        />,
      );
    });

    const addButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.includes('Add'),
    );
    assert.ok(addButton, 'expected an add button in the preview window header');

    await act(async () => {
      addButton.dispatchEvent(
        new dom.window.MouseEvent('click', {
          bubbles: true,
          cancelable: true,
        }),
      );
    });

    assert.deepEqual(addedFiles, [robotFile.name]);
  } finally {
    await act(async () => {
      root.unmount();
    });
    dom.window.close();
  }
});

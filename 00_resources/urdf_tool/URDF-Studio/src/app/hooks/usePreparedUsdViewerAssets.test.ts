import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import { DEFAULT_LINK, GeometryType, type AssemblyState, type RobotFile } from '@/types';
import { resolveImportedAssetPath } from '@/core/parsers/meshPathUtils';
import {
  buildPreparedUsdViewerAssetDescriptors,
  buildProjectedAssemblyViewerAssetAliases,
  usePreparedUsdViewerAssets,
} from './usePreparedUsdViewerAssets.ts';

function installDom() {
  const previous = {
    window: globalThis.window,
    document: globalThis.document,
    navigator: globalThis.navigator,
    HTMLElement: globalThis.HTMLElement,
    Node: globalThis.Node,
    actEnvironment: (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean })
      .IS_REACT_ACT_ENVIRONMENT,
  };
  const dom = new JSDOM('<!doctype html><html><body></body></html>');
  const setGlobal = (key: string, value: unknown) => Object.defineProperty(globalThis, key, {
    configurable: true,
    writable: true,
    value,
  });
  setGlobal('window', dom.window);
  setGlobal('document', dom.window.document);
  setGlobal('navigator', dom.window.navigator);
  setGlobal('HTMLElement', dom.window.HTMLElement);
  setGlobal('Node', dom.window.Node);
  setGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  return () => {
    dom.window.close();
    const restore = (key: string, value: unknown) => {
      if (value === undefined) {
        delete (globalThis as Record<string, unknown>)[key];
        return;
      }
      setGlobal(key, value);
    };
    restore('window', previous.window);
    restore('document', previous.document);
    restore('navigator', previous.navigator);
    restore('HTMLElement', previous.HTMLElement);
    restore('Node', previous.Node);
    restore('IS_REACT_ACT_ENVIRONMENT', previous.actEnvironment);
  };
}

async function renderPreparedAssetsProbe(onRender: () => void) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  function Probe() {
    onRender();
    usePreparedUsdViewerAssets({
      assemblyState: null,
      assets: {},
      availableFiles: [],
      additionalSourceFiles: [],
      preparedExportCaches: {},
      getUsdPreparedExportCache: () => null,
    });
    return null;
  }
  await act(async () => root.render(React.createElement(Probe)));
  return async () => {
    await act(async () => root.unmount());
    container.remove();
  };
}

function createUsdFile(name: string): RobotFile {
  return {
    name,
    format: 'usd',
    content: '',
  };
}

test('buildPreparedUsdViewerAssetDescriptors includes explicit USD source files outside assembly mode', () => {
  const sourceFile = createUsdFile('unitree_model/B2/usd/b2.viewer_roundtrip.usd');
  const meshBlob = new Blob(['obj-data'], { type: 'text/plain' });

  const descriptors = buildPreparedUsdViewerAssetDescriptors({
    assemblyState: null,
    availableFiles: [sourceFile],
    additionalSourceFiles: [sourceFile],
    getUsdPreparedExportCache: (path) =>
      path === sourceFile.name
        ? {
            meshFiles: {
              FR_calf_visual_0_section_0: meshBlob,
              'FR_calf_visual_0_section_0.obj': meshBlob,
            },
          }
        : null,
  });

  assert.deepEqual(descriptors, [
    {
      assetPath: resolveImportedAssetPath('FR_calf_visual_0_section_0', sourceFile.name),
      blob: meshBlob,
      cacheKey: `${sourceFile.name}::FR_calf_visual_0_section_0`,
    },
    {
      assetPath: resolveImportedAssetPath('FR_calf_visual_0_section_0.obj', sourceFile.name),
      blob: meshBlob,
      cacheKey: `${sourceFile.name}::FR_calf_visual_0_section_0.obj`,
    },
  ]);
});

test('usePreparedUsdViewerAssets does not loop when callers pass fresh empty collections', async () => {
  const restoreDom = installDom();
  let renderCount = 0;
  let cleanup: (() => Promise<void>) | null = null;

  try {
    cleanup = await renderPreparedAssetsProbe(() => { renderCount += 1; });
    assert.equal(renderCount, 1);
  } finally {
    await cleanup?.();
    restoreDom();
  }
});

test('buildPreparedUsdViewerAssetDescriptors keeps same-basename USD component meshes distinct', () => {
  const leftFile = createUsdFile('robots/left.usd');
  const rightFile = createUsdFile('robots/right.usd');
  const leftBlob = new Blob(['left'], { type: 'text/plain' });
  const rightBlob = new Blob(['right'], { type: 'text/plain' });
  const createComponent = (id: string, sourceFile: string) => ({
    id,
    name: id,
    sourceFile,
    visible: true,
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    robot: {
      name: id,
      rootLinkId: 'base_link',
      links: {
        base_link: {
          ...structuredClone(DEFAULT_LINK),
          id: 'base_link',
          name: 'base_link',
          visual: {
            ...structuredClone(DEFAULT_LINK.visual),
            type: GeometryType.MESH,
            meshPath: 'base_link_visual_0.obj',
          },
        },
      },
      joints: {},
    },
  });
  const assemblyState: AssemblyState = {
    name: 'multi-usd',
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    components: {
      left: createComponent('left', leftFile.name),
      right: createComponent('right', rightFile.name),
    },
    bridges: {},
  };

  const descriptors = buildPreparedUsdViewerAssetDescriptors({
    assemblyState,
    availableFiles: [leftFile, rightFile],
    getUsdPreparedExportCache: (path) => ({
      meshFiles: {
        'base_link_visual_0.obj': path === leftFile.name ? leftBlob : rightBlob,
      },
    }),
  });

  assert.equal(descriptors.length, 2);
  assert.notEqual(descriptors[0]!.assetPath, descriptors[1]!.assetPath);
  assert.match(descriptors[0]!.assetPath, /^__workspace__\/components\//);
  assert.match(descriptors[1]!.assetPath, /^__workspace__\/components\//);
  assert.deepEqual(new Set(descriptors.map((entry) => entry.blob)), new Set([leftBlob, rightBlob]));
});

test('assembled USD descriptors retain an unscoped alias for previewing a component source', () => {
  const leftFile = createUsdFile('robots/left.usd');
  const rightFile = createUsdFile('robots/right.usd');
  const leftBlob = new Blob(['left'], { type: 'text/plain' });
  const createComponent = (id: string, sourceFile: string) => ({
    id,
    name: id,
    sourceFile,
    visible: true,
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    robot: {
      name: id,
      rootLinkId: 'base_link',
      links: {
        base_link: {
          ...structuredClone(DEFAULT_LINK),
          id: 'base_link',
          name: 'base_link',
        },
      },
      joints: {},
    },
  });
  const assemblyState: AssemblyState = {
    name: 'multi-usd-preview',
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    components: {
      left: createComponent('left', leftFile.name),
      right: createComponent('right', rightFile.name),
    },
    bridges: {},
  };

  const descriptors = buildPreparedUsdViewerAssetDescriptors({
    assemblyState,
    availableFiles: [leftFile, rightFile],
    additionalSourceFiles: [leftFile],
    getUsdPreparedExportCache: (path) => ({
      meshFiles: {
        'base_link_visual_0.obj': path === leftFile.name ? leftBlob : new Blob(['right']),
      },
    }),
  });
  const leftDescriptors = descriptors.filter((entry) => entry.blob === leftBlob);

  assert.equal(leftDescriptors.length, 2);
  assert.ok(leftDescriptors.some((entry) => entry.assetPath.startsWith('__workspace__/components/')));
  assert.ok(leftDescriptors.some(
    (entry) => entry.assetPath === resolveImportedAssetPath(
      'base_link_visual_0.obj',
      leftFile.name,
    ),
  ));
});

test('buildProjectedAssemblyViewerAssetAliases scopes same-name USD textures to their component', () => {
  const leftFile = createUsdFile('robots/left/model.usd');
  const rightFile = createUsdFile('robots/right/model.usd');
  const createComponent = (id: string, sourceFile: string) => {
    const visual = {
      ...structuredClone(DEFAULT_LINK.visual),
      type: GeometryType.MESH,
      meshPath: 'base_link_visual_0.obj',
      authoredMaterials: [{ texture: 'base_color.png' }],
    };
    return {
      id,
      name: id,
      sourceFile,
      visible: true,
      transform: {
        position: { x: 0, y: 0, z: 0 },
        rotation: { r: 0, p: 0, y: 0 },
      },
      robot: {
        name: id,
        rootLinkId: 'base_link',
        links: {
          base_link: {
            ...structuredClone(DEFAULT_LINK),
            id: 'base_link',
            name: 'base_link',
            visual,
          },
        },
        joints: {},
      },
    };
  };
  const assemblyState: AssemblyState = {
    name: 'textured-usd',
    transform: {
      position: { x: 0, y: 0, z: 0 },
      rotation: { r: 0, p: 0, y: 0 },
    },
    components: {
      left: createComponent('left', leftFile.name),
      right: createComponent('right', rightFile.name),
    },
    bridges: {},
  };
  const aliases = buildProjectedAssemblyViewerAssetAliases({
    assemblyState,
    assets: {
      'robots/left/base_color.png': 'blob:left-texture',
      'robots/right/base_color.png': 'blob:right-texture',
    },
  });

  assert.equal(Object.keys(aliases).length, 2);
  assert.deepEqual(new Set(Object.values(aliases)), new Set([
    'blob:left-texture',
    'blob:right-texture',
  ]));
  assert.ok(Object.keys(aliases).every((path) => path.startsWith('__workspace__/components/')));
});

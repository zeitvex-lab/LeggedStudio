import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import type { RobotState, UrdfLink } from '@/types';
import { GeometryType } from '@/types';
import { translations } from '@/shared/i18n';
import { useCollisionTransformStore } from '@/store/collisionTransformStore';
import { useSelectionStore } from '@/store/selectionStore';
import { useUIStore } from '@/store/uiStore';
import { GeometryEditor } from './GeometryEditor.tsx';
import { __resetMeshAnalysisWorkerBridgeForTests } from '../utils/meshAnalysisWorkerBridge.ts';

type WorkerEventHandler = (event: { data?: unknown; error?: unknown; message?: string }) => void;

class FakeWorker {
  private readonly listeners = new Map<string, Set<WorkerEventHandler>>();

  public readonly postedMessages: unknown[] = [];

  addEventListener(type: string, handler: WorkerEventHandler): void {
    const handlers = this.listeners.get(type) ?? new Set<WorkerEventHandler>();
    handlers.add(handler);
    this.listeners.set(type, handlers);
  }

  removeEventListener(type: string, handler: WorkerEventHandler): void {
    this.listeners.get(type)?.delete(handler);
  }

  postMessage(message: unknown): void {
    this.postedMessages.push(message);
  }

  terminate(): void {}

  emitMessage(data: unknown): void {
    this.listeners.get('message')?.forEach((handler) => {
      handler({ data });
    });
  }

  emitError(error: Error): void {
    this.listeners.get('error')?.forEach((handler) => {
      handler({ error, message: error.message });
    });
  }
}

const MATCHED_VISUAL_MESH_ORIGIN = {
  xyz: { x: 0.1, y: 0.2, z: -0.05 },
  rpy: { r: 0.35, p: -0.4, y: 0.55 },
} as const;

const MATCHED_VISUAL_MESH_ANALYSIS = {
  bounds: {
    x: 0.82,
    y: 0.21,
    z: 0.18,
    cx: 0,
    cy: 0,
    cz: 0,
  },
  primitiveFits: {
    cylinder: {
      axis: { x: 1, y: 0, z: 0 },
      center: { x: 0, y: 0, z: 0 },
      radius: 0.07,
      length: 0.92,
      volume: 0.014185086476958216,
    },
    capsule: {
      axis: { x: 1, y: 0, z: 0 },
      center: { x: 0, y: 0, z: 0 },
      radius: 0.07,
      length: 0.92,
      volume: 0.020357520395261863,
    },
  },
} as const;

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
  (globalThis as { HTMLInputElement?: typeof HTMLInputElement }).HTMLInputElement =
    dom.window.HTMLInputElement;
  (globalThis as { Node?: typeof Node }).Node = dom.window.Node;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { MouseEvent?: typeof MouseEvent }).MouseEvent = dom.window.MouseEvent;
  (globalThis as { PointerEvent?: typeof PointerEvent }).PointerEvent =
    dom.window.PointerEvent ?? dom.window.MouseEvent;
  (globalThis as { InputEvent?: typeof InputEvent }).InputEvent = dom.window.InputEvent;
  (globalThis as { FocusEvent?: typeof FocusEvent }).FocusEvent = dom.window.FocusEvent;
  (globalThis as { KeyboardEvent?: typeof KeyboardEvent }).KeyboardEvent = dom.window.KeyboardEvent;
  (globalThis as { ResizeObserver?: typeof ResizeObserver }).ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  (globalThis as { getComputedStyle?: typeof getComputedStyle }).getComputedStyle =
    dom.window.getComputedStyle.bind(dom.window);
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  if (!('attachEvent' in dom.window.HTMLElement.prototype)) {
    Object.defineProperty(dom.window.HTMLElement.prototype, 'attachEvent', {
      value: () => {},
      configurable: true,
    });
  }
  if (!('detachEvent' in dom.window.HTMLElement.prototype)) {
    Object.defineProperty(dom.window.HTMLElement.prototype, 'detachEvent', {
      value: () => {},
      configurable: true,
    });
  }

  return dom;
}

function resetGeometryEditorTestState() {
  __resetMeshAnalysisWorkerBridgeForTests();
  useCollisionTransformStore.setState({ pendingCollisionTransform: null });
  useSelectionStore.setState({
    selection: null,
    hoveredSelection: null,
    deferredHoveredSelection: null,
    hoverFrozen: false,
    attentionSelection: null,
    focusTarget: null,
    interactionGuard: null,
  });
  useUIStore.setState({ rotationDisplayMode: 'euler_deg' });
}

function createComponentRoot() {
  resetGeometryEditorTestState();
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  return { dom, container, root };
}

async function destroyComponentRoot(dom: JSDOM, root: Root) {
  await act(async () => {
    root.unmount();
  });
  resetGeometryEditorTestState();
  dom.window.close();
}

function createLink(secondaryColor: string): UrdfLink {
  return {
    id: 'base_link',
    name: 'base_link',
    visible: true,
    visual: {
      type: GeometryType.BOX,
      dimensions: { x: 0.4, y: 0.3, z: 0.2 },
      color: '#ff0000',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    visualBodies: [
      {
        type: GeometryType.BOX,
        dimensions: { x: 0.2, y: 0.2, z: 0.2 },
        color: secondaryColor,
        origin: { xyz: { x: 0.1, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      },
    ],
    collision: {
      type: GeometryType.NONE,
      dimensions: { x: 0, y: 0, z: 0 },
      color: '#ef4444',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    },
    collisionBodies: [],
    inertial: {
      mass: 1,
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
      inertia: { ixx: 1, ixy: 0, ixz: 0, iyy: 1, iyz: 0, izz: 1 },
    },
  };
}

function createMultiMaterialMeshLink(): UrdfLink {
  const link = createLink('#00ff00');
  link.visual = {
    ...link.visual,
    type: GeometryType.MESH,
    dimensions: { x: 1, y: 1, z: 1 },
    meshPath: 'meshes/base_link.dae',
    authoredMaterials: [
      { name: 'body', color: '#bebebe' },
      { name: 'trim', color: '#ffffff' },
      { name: 'fastener', color: '#000000' },
      { name: 'accent', color: '#000000' },
    ],
  };
  (link.visual as { color?: string }).color = undefined;
  return link;
}

function createCollisionVisualMeshReferenceLink(
  secondaryCollisionType: GeometryType = GeometryType.SPHERE,
  meshPathSuffix = 'secondary-link',
): UrdfLink {
  const link = createLink('#00ff00');
  link.visual = {
    type: GeometryType.MESH,
    meshPath: 'meshes/primary-link.dae',
    dimensions: { x: 1, y: 1, z: 1 },
    color: '#ff0000',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
  };
  link.visualBodies = [
    {
      type: GeometryType.MESH,
      meshPath: `meshes/${meshPathSuffix}.dae`,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#00ff00',
      origin: {
        xyz: { ...MATCHED_VISUAL_MESH_ORIGIN.xyz },
        rpy: { ...MATCHED_VISUAL_MESH_ORIGIN.rpy },
      },
    },
  ];
  link.collision = {
    type: GeometryType.SPHERE,
    dimensions: { x: 0.1, y: 0.1, z: 0.1 },
    color: '#ef4444',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
  };
  link.collisionBodies = [
    {
      type: secondaryCollisionType,
      dimensions:
        secondaryCollisionType === GeometryType.BOX
          ? { x: 0.08, y: 0.08, z: 0.08 }
          : { x: 0.08, y: 0.08, z: 0.08 },
      color: '#ef4444',
      origin: {
        xyz: { ...MATCHED_VISUAL_MESH_ORIGIN.xyz },
        rpy: { r: 0, p: 0, y: 0 },
      },
    },
  ];
  return link;
}

function createCollisionMeshStemReferenceLink(): UrdfLink {
  const link = createLink('#00ff00');
  link.visual = {
    type: GeometryType.MESH,
    meshPath: 'meshes/root_visual.dae',
    dimensions: { x: 1, y: 1, z: 1 },
    color: '#ff0000',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
  };
  link.visualBodies = [
    {
      type: GeometryType.MESH,
      meshPath: 'meshes/shoulder_visual.dae',
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#00ff00',
      origin: {
        xyz: { x: 0.2, y: 0.1, z: 0.05 },
        rpy: { r: 0.1, p: 0.2, y: 0.3 },
      },
    },
    {
      type: GeometryType.MESH,
      meshPath: 'meshes/forearm_visual.dae',
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#00ccff',
      origin: {
        xyz: { x: 0.6, y: -0.15, z: 0.12 },
        rpy: { r: -0.25, p: 0.45, y: -0.35 },
      },
    },
  ];
  link.collision = {
    type: GeometryType.SPHERE,
    dimensions: { x: 0.1, y: 0.1, z: 0.1 },
    color: '#ef4444',
    origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
  };
  link.collisionBodies = [
    {
      type: GeometryType.MESH,
      meshPath: 'meshes/forearm_collision.dae',
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ef4444',
      origin: {
        xyz: { x: 0.2, y: 0.1, z: 0.05 },
        rpy: { r: 0, p: 0, y: 0 },
      },
    },
  ];
  return link;
}

function createRobot(link: UrdfLink): RobotState {
  return {
    name: 'demo',
    links: {
      [link.id]: link,
    },
    joints: {},
    rootLinkId: link.id,
    selection: {
      type: 'link',
      id: link.id,
      subType: 'visual',
      objectIndex: 1,
    },
  };
}

function getReactProps(node: Element): Record<string, unknown> {
  const reactPropsKey = Object.keys(node).find((key) => key.startsWith('__reactProps$'));
  assert.ok(reactPropsKey, 'React props key should exist on rendered element');
  return (node as unknown as Record<string, unknown>)[reactPropsKey] as Record<string, unknown>;
}

function setInputValue(input: HTMLInputElement, value: string) {
  const prototype = input.ownerDocument.defaultView?.HTMLInputElement.prototype;
  const valueSetter = prototype
    ? Object.getOwnPropertyDescriptor(prototype, 'value')?.set
    : undefined;

  assert.ok(valueSetter, 'HTMLInputElement value setter should exist');
  valueSetter.call(input, value);
}

function dispatchReactChange(input: HTMLInputElement, value: string) {
  setInputValue(input, value);
  const reactProps = getReactProps(input);
  const onChange = reactProps.onChange;
  assert.equal(typeof onChange, 'function', 'React onChange handler should exist');

  (onChange as (event: { target: HTMLInputElement; currentTarget: HTMLInputElement }) => void)({
    target: input,
    currentTarget: input,
  });
}

function dispatchReactBlur(input: HTMLInputElement) {
  const reactProps = getReactProps(input);
  const onBlur = reactProps.onBlur;
  assert.equal(typeof onBlur, 'function', 'React onBlur handler should exist');

  (onBlur as (event: { target: HTMLInputElement; currentTarget: HTMLInputElement }) => void)({
    target: input,
    currentTarget: input,
  });
}

async function commitColorPickerValue(input: HTMLInputElement, value: string) {
  await act(async () => {
    dispatchReactChange(input, value);
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

function dispatchReactSelectChange(select: HTMLSelectElement, value: string) {
  const prototype = select.ownerDocument.defaultView?.HTMLSelectElement.prototype;
  const valueSetter = prototype
    ? Object.getOwnPropertyDescriptor(prototype, 'value')?.set
    : undefined;

  assert.ok(valueSetter, 'HTMLSelectElement value setter should exist');
  valueSetter.call(select, value);

  const reactProps = getReactProps(select);
  const onChange = reactProps.onChange;
  assert.equal(typeof onChange, 'function', 'React onChange handler should exist');

  (onChange as (event: { target: HTMLSelectElement; currentTarget: HTMLSelectElement }) => void)({
    target: select,
    currentTarget: select,
  });
}

function getColorInput(container: Element): HTMLInputElement {
  const input = container.querySelector('input[type="color"][aria-label="Color"]');
  assert.ok(input, 'color input should exist');
  return input as HTMLInputElement;
}

function getOpacityInput(container: Element, expectedValue: string): HTMLInputElement {
  const input = Array.from(container.querySelectorAll('input[inputmode="decimal"]')).find(
    (candidate) => (candidate as HTMLInputElement).value === expectedValue,
  );
  assert.ok(input, `opacity input with value ${expectedValue} should exist`);
  return input as HTMLInputElement;
}

async function waitForWorkerPost(dom: JSDOM, fakeWorker: FakeWorker): Promise<void> {
  for (let attempt = 0; attempt < 3 && fakeWorker.postedMessages.length === 0; attempt += 1) {
    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });
  }
}

function emitMeshAnalysisResult(fakeWorker: FakeWorker): void {
  const workerRequest = fakeWorker.postedMessages.at(-1) as {
    requestId: number;
    tasks: Array<{ targetId: string; cacheKey: string; meshPath: string }>;
  };

  fakeWorker.emitMessage({
    type: 'batch-result',
    requestId: workerRequest.requestId,
    results: [
      {
        targetId: workerRequest.tasks[0]?.targetId,
        cacheKey: workerRequest.tasks[0]?.cacheKey,
        analysis: MATCHED_VISUAL_MESH_ANALYSIS,
      },
    ],
  });
}

async function renderGeometryEditor(
  root: Root,
  link: UrdfLink,
  onUpdate: (nextLink: UrdfLink) => void,
  robot: RobotState = createRobot(link),
  category: 'visual' | 'collision' = 'visual',
  options: {
    assets?: Record<string, string>;
    onUploadAsset?: (file: File) => void;
    onDeleteAsset?: (path: string) => void;
    sourceFilePath?: string;
  } = {},
) {
  await act(async () => {
    root.render(
      React.createElement(GeometryEditor, {
        componentId: 'test-component',
        data: link,
        robot,
        category,
        onUpdate,
        assets: options.assets ?? {},
        onUploadAsset: options.onUploadAsset ?? (() => {}),
        onDeleteAsset: options.onDeleteAsset ?? (() => {}),
        onLinkNameChange: () => {},
        t: translations.en,
        lang: 'en',
        isTabbed: true,
        sourceFilePath: options.sourceFilePath,
      } as unknown as React.ComponentProps<typeof GeometryEditor>),
    );
  });
}

async function clickElement(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

async function doubleClickElement(element: Element) {
  await act(async () => {
    element.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
  });
}

test('GeometryEditor reads and updates the selected visual objectIndex instead of always using the primary visual', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(root, link, (nextLink) => {
      updates.push(nextLink);
    });

    const colorInput = getColorInput(container);
    assert.equal(colorInput.value.toLowerCase(), '#00ff00');

    await commitColorPickerValue(colorInput, '#abcdef');

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'GeometryEditor should emit an updated link');
    assert.equal(nextLink.visual.color, '#ff0000');
    assert.equal(nextLink.visualBodies?.[0]?.color, '#abcdef');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor defers visual color picker updates until the picker is committed', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(root, link, (nextLink) => {
      updates.push(nextLink);
    });

    const colorInput = getColorInput(container);

    await act(async () => {
      dispatchReactChange(colorInput, '#abcdef');
      dispatchReactChange(colorInput, '#123456');
    });

    assert.equal(updates.length, 0, 'dragging the color picker should stay local');

    await act(async () => {
      colorInput.dispatchEvent(new Event('change', { bubbles: true }));
    });

    assert.equal(updates.length, 1);
    assert.equal(updates[0]?.visualBodies?.[0]?.color, '#123456');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor exposes the geometry type selector through the shared combobox trigger', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');

    await renderGeometryEditor(root, link, () => {});

    const typeCombobox = container.querySelector(
      'button[role="combobox"][aria-label="Type"]',
    ) as HTMLButtonElement | null;

    assert.ok(typeCombobox, 'expected the geometry type field to render the shared combobox');
    assert.match(typeCombobox.className, /\bbg-input-bg\b/);
    assert.match(typeCombobox.className, /\bborder-border-strong\b/);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor exposes ellipsoid as a first-class geometry type with per-axis radii controls', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    link.visual = {
      type: GeometryType.ELLIPSOID,
      dimensions: { x: 0.03, y: 0.04, z: 0.02 },
      color: '#ff0000',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;

    await renderGeometryEditor(
      root,
      link,
      () => {
        throw new Error('ellipsoid rendering test should not emit updates without user edits');
      },
      robot,
    );

    const typeSelect = container.querySelector('select');
    assert.ok(typeSelect, 'geometry type select should exist');
    assert.equal((typeSelect as HTMLSelectElement).value, GeometryType.ELLIPSOID);
    assert.ok(container.textContent?.includes('Ellipsoid'));
    assert.ok(container.textContent?.includes('Radius X'));
    assert.ok(container.textContent?.includes('Radius Y'));
    assert.ok(container.textContent?.includes('Radius Z'));
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor preserves plane and hfield types as explicit MJCF geometry kinds', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const planeLink = createLink('#00ff00');
    planeLink.visual = {
      type: GeometryType.PLANE,
      dimensions: { x: 6, y: 4, z: 0 },
      color: '#ff0000',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };

    const planeRobot = createRobot(planeLink);
    planeRobot.selection.objectIndex = 0;

    await renderGeometryEditor(
      root,
      planeLink,
      () => {
        throw new Error('plane rendering test should not emit updates without user edits');
      },
      planeRobot,
    );

    const planeSelect = container.querySelector('select');
    assert.ok(planeSelect, 'geometry type select should exist for plane');
    assert.equal((planeSelect as HTMLSelectElement).value, GeometryType.PLANE);
    assert.ok(container.textContent?.includes('Plane'));
    assert.ok(container.textContent?.includes('Width'));
    assert.ok(container.textContent?.includes('Depth'));

    const hfieldLink = createLink('#00ff00');
    hfieldLink.visual = {
      type: GeometryType.HFIELD,
      dimensions: { x: 1, y: 1, z: 0 },
      color: '#ff0000',
      assetRef: 'terrain_patch',
      mjcfHfield: {
        name: 'terrain_patch',
        file: 'terrain.png',
        contentType: 'image/png',
        nrow: 32,
        ncol: 48,
        size: {
          radiusX: 2,
          radiusY: 3,
          elevationZ: 0.4,
          baseZ: 0.1,
        },
      },
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };

    const hfieldRobot = createRobot(hfieldLink);
    hfieldRobot.selection.objectIndex = 0;

    await renderGeometryEditor(
      root,
      hfieldLink,
      () => {
        throw new Error('hfield rendering test should not emit updates without user edits');
      },
      hfieldRobot,
    );

    const hfieldSelect = container.querySelector('select');
    assert.ok(hfieldSelect, 'geometry type select should exist for hfield');
    assert.equal((hfieldSelect as HTMLSelectElement).value, GeometryType.HFIELD);
    assert.ok(container.textContent?.includes('Height Field'));
    assert.ok(container.textContent?.includes('Asset Reference'));
    assert.ok(container.textContent?.includes('terrain_patch'));
    assert.ok(container.textContent?.includes('terrain.png'));
    assert.ok(container.textContent?.includes('Content Type'));
    assert.ok(container.textContent?.includes('image/png'));
    assert.ok(container.textContent?.includes('Rows: 32'));
    assert.ok(container.textContent?.includes('Cols: 48'));
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor keeps the type and name header responsive for visual and collision geometry', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    for (const category of ['visual', 'collision'] as const) {
      const link = createLink('#00ff00');
      const robot = createRobot(link);
      robot.selection = {
        type: 'link',
        id: link.id,
        subType: category,
        objectIndex: 0,
      };

      await renderGeometryEditor(root, link, () => {}, robot, category);

      const typeLabel = Array.from(container.querySelectorAll('span')).find(
        (node) => node.textContent === translations.en.type,
      );
      assert.ok(typeLabel, `${category} geometry should render the type label`);

      const sharedRow = typeLabel.parentElement?.parentElement;
      assert.ok(sharedRow, `${category} geometry should render the shared header row`);

      const nameLabel = Array.from(sharedRow.querySelectorAll('span')).find(
        (node) => node.textContent === translations.en.name,
      );
      assert.ok(nameLabel, `${category} geometry should render the name label`);

      assert.equal(
        nameLabel.parentElement?.parentElement,
        sharedRow,
        `${category} geometry should keep type and name on the same row`,
      );
      assert.match(
        sharedRow.className,
        /\bgap-1\.5\b/,
        `${category} geometry should keep the header spacing aligned with the other property rows`,
      );

      const geometryTypeSelect = container.querySelector(
        `button[role="combobox"][aria-label="${translations.en.type}"], select[aria-label="${translations.en.type}"]`,
      );
      assert.ok(geometryTypeSelect, `${category} geometry should render the type select`);
      assert.doesNotMatch(
        geometryTypeSelect.className,
        /\bw-28\b/,
        `${category} geometry should not pin the type select to a fixed width`,
      );
      assert.doesNotMatch(
        geometryTypeSelect.className,
        /\bshrink-0\b/,
        `${category} geometry type select should be allowed to shrink with the row`,
      );

      assert.match(
        sharedRow.className,
        /\bmin-w-0\b/,
        `${category} geometry header row should stay shrinkable inside narrow sidebars`,
      );

      const geometryNameInput = container.querySelector(
        'input[type="text"][spellcheck="false"]',
      ) as HTMLInputElement | null;
      assert.ok(geometryNameInput, `${category} geometry should render the name input`);
      assert.match(
        geometryNameInput.className,
        /\bflex-1\b/,
        `${category} geometry name input should fill the available width inside the shared row`,
      );
    }
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor renders mesh scale as a single inline XYZ row without stepper buttons', async () => {
  const { dom, container, root } = createComponentRoot();
  const originalWorker = globalThis.Worker;
  const fakeWorker = new FakeWorker();

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: class {
      constructor() {
        return fakeWorker as unknown as Worker;
      }
    },
  });

  try {
    const link = createLink('#00ff00');
    link.visual = {
      type: GeometryType.MESH,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ff0000',
      meshPath: 'meshes/base_link.dae',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;

    await renderGeometryEditor(root, link, () => {}, robot);

    const meshScaleLabel = Array.from(container.querySelectorAll('label')).find(
      (node) => node.textContent?.trim() === translations.en.meshScale,
    );
    assert.ok(meshScaleLabel, 'mesh scale label should render');

    const meshScaleSection = meshScaleLabel.parentElement;
    assert.ok(meshScaleSection, 'mesh scale section should render');

    const meshScaleInlineRows = Array.from(meshScaleSection.querySelectorAll('div')).filter(
      (node) =>
        node.className.includes('flex') &&
        node.className.includes('min-w-0') &&
        node.className.includes('items-center') &&
        node.className.includes('gap-1.5'),
    );
    assert.equal(meshScaleInlineRows.length, 3, 'mesh scale should render three inline axis rows');

    const meshScaleAxisCounts = Array.from(meshScaleSection.querySelectorAll('span')).reduce(
      (counts, node) => {
        const label = node.textContent?.trim();
        if (label === 'X' || label === 'Y' || label === 'Z') {
          counts[label] += 1;
        }
        return counts;
      },
      { X: 0, Y: 0, Z: 0 },
    );
    assert.deepEqual(
      meshScaleAxisCounts,
      { X: 1, Y: 1, Z: 1 },
      'mesh scale should only render one visible XYZ label set',
    );

    const xInput = meshScaleSection.querySelectorAll('input[type="text"]').item(0);
    const yInput = meshScaleSection.querySelectorAll('input[type="text"]').item(1);
    const zInput = meshScaleSection.querySelectorAll('input[type="text"]').item(2);
    assert.ok(xInput, 'mesh scale X input should render');
    assert.ok(yInput, 'mesh scale Y input should render');
    assert.ok(zInput, 'mesh scale Z input should render');

    const meshScaleStepperButtons = meshScaleSection.querySelectorAll(
      'button[aria-label^="Increase"], button[aria-label^="Decrease"]',
    );
    assert.equal(
      meshScaleStepperButtons.length,
      0,
      'mesh scale inputs should not render increment or decrement stepper buttons',
    );
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor adds compact +/-90 degree collision rotation shortcuts for each axis', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    useUIStore.setState({ rotationDisplayMode: 'euler_deg' });

    const link = createLink('#00ff00');
    link.collision = {
      type: GeometryType.CAPSULE,
      dimensions: { x: 0.05, y: 0.5, z: 0.05 },
      color: '#ef4444',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 0,
    };
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'collision',
    );

    const rollDecreaseButton = container.querySelector('button[aria-label="Roll decrease 90°"]');
    const rollIncreaseButton = container.querySelector('button[aria-label="Roll increase 90°"]');
    assert.ok(
      rollDecreaseButton,
      'roll decrease shortcut button should exist for collision geometry',
    );
    assert.ok(
      rollIncreaseButton,
      'roll increase shortcut button should exist for collision geometry',
    );
    assert.equal(container.querySelector('button[aria-label="Roll increase 180°"]'), null);
    assert.equal(container.querySelector('button[aria-label="Roll reset 0°"]'), null);
    assert.equal(container.textContent?.includes('-90'), true);
    assert.equal(container.textContent?.includes('+90'), true);

    await act(async () => {
      rollDecreaseButton.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    const firstUpdatedLink = updates.at(-1);
    assert.ok(firstUpdatedLink, 'first collision rotation shortcut click should emit an update');
    assert.equal(firstUpdatedLink.collision.origin?.rpy.r, -Math.PI / 2);
    assert.equal(firstUpdatedLink.collision.origin?.rpy.p, 0);
    assert.equal(firstUpdatedLink.collision.origin?.rpy.y, 0);

    const updatedRobot = createRobot(firstUpdatedLink);
    updatedRobot.selection = {
      type: 'link',
      id: firstUpdatedLink.id,
      subType: 'collision',
      objectIndex: 0,
    };

    await renderGeometryEditor(
      root,
      firstUpdatedLink,
      (nextLink) => {
        updates.push(nextLink);
      },
      updatedRobot,
      'collision',
    );

    const rerenderedRollIncreaseButton = container.querySelector(
      'button[aria-label="Roll increase 90°"]',
    );
    assert.ok(
      rerenderedRollIncreaseButton,
      'roll increase shortcut button should still exist after the first update',
    );

    await act(async () => {
      rerenderedRollIncreaseButton.dispatchEvent(
        new dom.window.MouseEvent('click', { bubbles: true }),
      );
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'collision rotation shortcut should emit updates');
    assert.equal(nextLink.collision.origin?.rpy.r, 0);
    assert.equal(nextLink.collision.origin?.rpy.p, 0);
    assert.equal(nextLink.collision.origin?.rpy.y, 0);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor reuses collision-style rotation shortcuts for visual geometry', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    useUIStore.setState({ rotationDisplayMode: 'euler_deg' });

    const link = createLink('#00ff00');
    link.visual = {
      type: GeometryType.CAPSULE,
      dimensions: { x: 0.05, y: 0.5, z: 0.05 },
      color: '#ff0000',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };

    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'visual',
      objectIndex: 0,
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'visual',
    );

    const rollIncreaseButton = container.querySelector('button[aria-label="Roll increase 90°"]');
    const yawDecreaseButton = container.querySelector('button[aria-label="Yaw decrease 90°"]');
    assert.ok(
      rollIncreaseButton,
      'visual geometry should expose the same roll shortcut UI as collision geometry',
    );
    assert.ok(
      yawDecreaseButton,
      'visual geometry should expose the same yaw shortcut UI as collision geometry',
    );

    await act(async () => {
      yawDecreaseButton.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'visual rotation shortcut should emit an updated link');
    assert.equal(nextLink.visual.origin?.rpy.r, 0);
    assert.equal(nextLink.visual.origin?.rpy.p, 0);
    assert.equal(nextLink.visual.origin?.rpy.y, -Math.PI / 2);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor adds compact +/-π/2 collision rotation shortcuts in radian mode', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    useUIStore.setState({ rotationDisplayMode: 'euler_rad' });

    const link = createLink('#00ff00');
    link.collision = {
      type: GeometryType.CAPSULE,
      dimensions: { x: 0.05, y: 0.5, z: 0.05 },
      color: '#ef4444',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 0,
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'collision',
    );

    const rollIncreaseButton = container.querySelector('button[aria-label="Roll increase π/2"]');
    assert.ok(
      rollIncreaseButton,
      'roll increase π/2 shortcut button should exist for collision geometry',
    );

    await act(async () => {
      rollIncreaseButton.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'collision radian rotation shortcut should emit updates');
    assert.equal(nextLink.collision.origin?.rpy.r, Math.PI / 2);
    assert.equal(nextLink.collision.origin?.rpy.p, 0);
    assert.equal(nextLink.collision.origin?.rpy.y, 0);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor uses the matching visual mesh orientation when converting a collision sphere to a cylinder', async () => {
  const { dom, container, root } = createComponentRoot();
  const originalWorker = globalThis.Worker;
  const fakeWorker = new FakeWorker();

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: class {
      constructor() {
        return fakeWorker as unknown as Worker;
      }
    },
  });

  try {
    const link = createLink('#00ff00');
    link.visual = {
      type: GeometryType.MESH,
      meshPath: 'meshes/primary-link.dae',
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#ff0000',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    link.visualBodies = [
      {
        type: GeometryType.MESH,
        meshPath: 'meshes/secondary-link.dae',
        dimensions: { x: 1, y: 1, z: 1 },
        color: '#00ff00',
        origin: {
          xyz: { x: 0.1, y: 0.2, z: -0.05 },
          rpy: { r: 0.35, p: -0.4, y: 0.55 },
        },
      },
    ];
    link.collision = {
      type: GeometryType.SPHERE,
      dimensions: { x: 0.1, y: 0.1, z: 0.1 },
      color: '#ef4444',
      origin: { xyz: { x: 0, y: 0, z: 0 }, rpy: { r: 0, p: 0, y: 0 } },
    };
    link.collisionBodies = [
      {
        type: GeometryType.SPHERE,
        dimensions: { x: 0.08, y: 0.08, z: 0.08 },
        color: '#ef4444',
        origin: {
          xyz: { x: 0.1, y: 0.2, z: -0.05 },
          rpy: { r: 0, p: 0, y: 0 },
        },
      },
    ];

    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 1,
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'collision',
    );

    const typeSelect = container.querySelector('select');
    assert.ok(typeSelect, 'geometry type select should exist');

    await act(async () => {
      dispatchReactSelectChange(typeSelect as HTMLSelectElement, GeometryType.CYLINDER);
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });

    for (let attempt = 0; attempt < 3 && fakeWorker.postedMessages.length === 0; attempt += 1) {
      await act(async () => {
        await Promise.resolve();
        await new Promise<void>((resolve) => {
          dom.window.requestAnimationFrame(() => resolve());
        });
      });
    }

    assert.equal(fakeWorker.postedMessages.length, 1);
    const workerRequest = fakeWorker.postedMessages[0] as {
      requestId: number;
      tasks: Array<{ targetId: string; cacheKey: string; meshPath: string }>;
    };
    assert.equal(workerRequest.tasks.length, 1);
    assert.equal(workerRequest.tasks[0]?.meshPath, 'meshes/secondary-link.dae');

    fakeWorker.emitMessage({
      type: 'batch-result',
      requestId: workerRequest.requestId,
      results: [
        {
          targetId: workerRequest.tasks[0]?.targetId,
          cacheKey: workerRequest.tasks[0]?.cacheKey,
          analysis: {
            bounds: {
              x: 0.82,
              y: 0.21,
              z: 0.18,
              cx: 0,
              cy: 0,
              cz: 0,
            },
            primitiveFits: {
              cylinder: {
                axis: { x: 1, y: 0, z: 0 },
                center: { x: 0, y: 0, z: 0 },
                radius: 0.07,
                length: 0.92,
                volume: 0.014185086476958216,
              },
            },
          },
        },
      ],
    });

    await act(async () => {
      await Promise.resolve();
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'collision type change should emit an updated link');
    assert.equal(nextLink.collision.type, GeometryType.SPHERE);
    assert.equal(nextLink.collisionBodies?.[0]?.type, GeometryType.CYLINDER);
    assert.deepEqual(nextLink.collisionBodies?.[0]?.origin?.rpy, link.visualBodies[0]?.origin?.rpy);
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    await destroyComponentRoot(dom, root);
  }
});

for (const targetType of [GeometryType.BOX, GeometryType.ELLIPSOID] as const) {
  test(`GeometryEditor uses the matching visual mesh orientation when converting a collision sphere to ${targetType}`, async () => {
    const { dom, container, root } = createComponentRoot();
    const originalWorker = globalThis.Worker;
    const fakeWorker = new FakeWorker();

    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: class {
        constructor() {
          return fakeWorker as unknown as Worker;
        }
      },
    });

    try {
      const link = createCollisionVisualMeshReferenceLink(
        GeometryType.SPHERE,
        `secondary-${targetType}`,
      );
      const robot = createRobot(link);
      robot.selection = {
        type: 'link',
        id: link.id,
        subType: 'collision',
        objectIndex: 1,
      };

      const updates: UrdfLink[] = [];
      await renderGeometryEditor(
        root,
        link,
        (nextLink) => {
          updates.push(nextLink);
        },
        robot,
        'collision',
      );

      const typeSelect = container.querySelector('select');
      assert.ok(typeSelect, 'geometry type select should exist');

      await act(async () => {
        dispatchReactSelectChange(typeSelect as HTMLSelectElement, targetType);
        await new Promise<void>((resolve) => {
          dom.window.requestAnimationFrame(() => resolve());
        });
      });

      await waitForWorkerPost(dom, fakeWorker);
      assert.equal(fakeWorker.postedMessages.length, 1);

      const workerRequest = fakeWorker.postedMessages[0] as {
        tasks: Array<{ meshPath: string }>;
      };
      assert.equal(workerRequest.tasks[0]?.meshPath, `meshes/secondary-${targetType}.dae`);

      emitMeshAnalysisResult(fakeWorker);

      await act(async () => {
        await Promise.resolve();
      });

      const nextLink = updates.at(-1);
      assert.ok(nextLink, 'collision type change should emit an updated link');
      assert.equal(nextLink.collisionBodies?.[0]?.type, targetType);
      assert.deepEqual(nextLink.collisionBodies?.[0]?.origin?.rpy, MATCHED_VISUAL_MESH_ORIGIN.rpy);
    } finally {
      Object.defineProperty(globalThis, 'Worker', {
        configurable: true,
        writable: true,
        value: originalWorker,
      });
      await destroyComponentRoot(dom, root);
    }
  });
}

for (const sourceType of [
  GeometryType.SPHERE,
  GeometryType.BOX,
  GeometryType.CYLINDER,
  GeometryType.ELLIPSOID,
  GeometryType.CAPSULE,
] as const) {
  for (const targetType of [
    GeometryType.BOX,
    GeometryType.CYLINDER,
    GeometryType.ELLIPSOID,
    GeometryType.CAPSULE,
  ] as const) {
    if (sourceType === targetType) {
      continue;
    }

    test(`GeometryEditor uses the matching visual mesh orientation when converting a collision ${sourceType} to ${targetType}`, async () => {
      const { dom, container, root } = createComponentRoot();
      const originalWorker = globalThis.Worker;
      const fakeWorker = new FakeWorker();

      Object.defineProperty(globalThis, 'Worker', {
        configurable: true,
        writable: true,
        value: class {
          constructor() {
            return fakeWorker as unknown as Worker;
          }
        },
      });

      try {
        const link = createCollisionVisualMeshReferenceLink(
          sourceType,
          `secondary-${sourceType}-to-${targetType}`,
        );
        const robot = createRobot(link);
        robot.selection = {
          type: 'link',
          id: link.id,
          subType: 'collision',
          objectIndex: 1,
        };

        const updates: UrdfLink[] = [];
        await renderGeometryEditor(
          root,
          link,
          (nextLink) => {
            updates.push(nextLink);
          },
          robot,
          'collision',
        );

        const typeSelect = container.querySelector('select');
        assert.ok(typeSelect, 'geometry type select should exist');

        await act(async () => {
          dispatchReactSelectChange(typeSelect as HTMLSelectElement, targetType);
          await new Promise<void>((resolve) => {
            dom.window.requestAnimationFrame(() => resolve());
          });
        });

        await waitForWorkerPost(dom, fakeWorker);
        assert.equal(fakeWorker.postedMessages.length, 1);

        const workerRequest = fakeWorker.postedMessages[0] as {
          tasks: Array<{ meshPath: string }>;
        };
        assert.equal(
          workerRequest.tasks[0]?.meshPath,
          `meshes/secondary-${sourceType}-to-${targetType}.dae`,
        );

        emitMeshAnalysisResult(fakeWorker);

        await act(async () => {
          await Promise.resolve();
        });

        const nextLink = updates.at(-1);
        assert.ok(nextLink, 'collision type change should emit an updated link');
        assert.equal(nextLink.collisionBodies?.[0]?.type, targetType);
        assert.deepEqual(
          nextLink.collisionBodies?.[0]?.origin?.rpy,
          MATCHED_VISUAL_MESH_ORIGIN.rpy,
        );
      } finally {
        Object.defineProperty(globalThis, 'Worker', {
          configurable: true,
          writable: true,
          value: originalWorker,
        });
        await destroyComponentRoot(dom, root);
      }
    });
  }
}

test('GeometryEditor restores the matched visual mesh when converting a collision cylinder back to mesh', async () => {
  const { dom, container, root } = createComponentRoot();
  const originalWorker = globalThis.Worker;
  const fakeWorker = new FakeWorker();

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: class {
      constructor() {
        return fakeWorker as unknown as Worker;
      }
    },
  });

  try {
    const link = createCollisionVisualMeshReferenceLink(
      GeometryType.CYLINDER,
      'secondary-cylinder-to-mesh',
    );
    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 1,
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'collision',
    );

    const typeSelect = container.querySelector('select');
    assert.ok(typeSelect, 'geometry type select should exist');

    await act(async () => {
      dispatchReactSelectChange(typeSelect as HTMLSelectElement, GeometryType.MESH);
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });

    await act(async () => {
      await Promise.resolve();
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });

    assert.equal(
      fakeWorker.postedMessages.length,
      0,
      'restoring the matched visual mesh should not require a mesh analysis worker',
    );

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'collision mesh restoration should emit an updated link');
    assert.equal(nextLink.collisionBodies?.[0]?.type, GeometryType.MESH);
    assert.equal(nextLink.collisionBodies?.[0]?.meshPath, 'meshes/secondary-cylinder-to-mesh.dae');
    assert.deepEqual(nextLink.collisionBodies?.[0]?.dimensions, link.visualBodies?.[0]?.dimensions);
    assert.deepEqual(nextLink.collisionBodies?.[0]?.origin, link.visualBodies?.[0]?.origin);
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor matches a collision mesh to its visual mesh by stem before falling back to objectIndex', async () => {
  const { dom, container, root } = createComponentRoot();
  const originalWorker = globalThis.Worker;
  const fakeWorker = new FakeWorker();

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: class {
      constructor() {
        return fakeWorker as unknown as Worker;
      }
    },
  });

  try {
    const link = createCollisionMeshStemReferenceLink();
    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 1,
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'collision',
    );

    const typeSelect = container.querySelector('select');
    assert.ok(typeSelect, 'geometry type select should exist');

    await act(async () => {
      dispatchReactSelectChange(typeSelect as HTMLSelectElement, GeometryType.CYLINDER);
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });

    await waitForWorkerPost(dom, fakeWorker);
    const workerPaths = fakeWorker.postedMessages.map(
      (message) => (message as { tasks?: Array<{ meshPath?: string }> }).tasks?.[0]?.meshPath,
    );
    assert.ok(workerPaths.includes('meshes/forearm_visual.dae'));
    assert.ok(!workerPaths.includes('meshes/shoulder_visual.dae'));

    const workerRequest = fakeWorker.postedMessages.find(
      (message) =>
        (message as { tasks?: Array<{ meshPath?: string }> }).tasks?.[0]?.meshPath ===
        'meshes/forearm_visual.dae',
    ) as {
      tasks: Array<{ meshPath: string }>;
    };
    assert.ok(workerRequest, 'expected a mesh analysis request for the matched visual mesh');

    emitMeshAnalysisResult(fakeWorker);

    await act(async () => {
      await Promise.resolve();
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'collision mesh conversion should emit an updated link');
    assert.equal(nextLink.collisionBodies?.[0]?.type, GeometryType.CYLINDER);
    assert.deepEqual(
      nextLink.collisionBodies?.[0]?.origin?.rpy,
      link.visualBodies?.[1]?.origin?.rpy,
    );
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor normalizes alpha colors for the picker while preserving alpha on color picker edits', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#12345680');
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(root, link, (nextLink) => {
      updates.push(nextLink);
    });

    const colorInput = getColorInput(container);
    assert.equal(colorInput.value.toLowerCase(), '#123456');

    await commitColorPickerValue(colorInput, '#abcdef');

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'GeometryEditor should emit an updated link');
    assert.equal(nextLink.visualBodies?.[0]?.color, '#abcdef80');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor exposes and updates material opacity for alpha colors', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#12345680');
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(root, link, (nextLink) => {
      updates.push(nextLink);
    });

    const opacityInput = getOpacityInput(container, '0.502');

    await act(async () => {
      dispatchReactChange(opacityInput, '0.25');
      dispatchReactBlur(opacityInput);
    });

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'GeometryEditor should emit an updated link');
    assert.deepEqual(nextLink.visualBodies?.[0]?.authoredMaterials?.[0], {
      color: '#12345640',
      opacity: 0.25,
    });
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor shows the effective legacy link material color when the primary visual has no inline color', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    link.visual = {
      ...link.visual,
    };
    Reflect.deleteProperty(link.visual, 'color');

    const robot = createRobot(link);
    robot.selection.objectIndex = 0;
    robot.materials = {
      base_link: {
        color: '#b2b2b2',
      },
    };

    await renderGeometryEditor(root, link, () => {}, robot);

    const colorInput = getColorInput(container);
    assert.equal(colorInput.value.toLowerCase(), '#b2b2b2');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor surfaces all paint material colors for primitive visuals', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#808080');
    link.visual = {
      ...link.visual,
      type: GeometryType.BOX,
      dimensions: { x: 1, y: 1, z: 1 },
      color: '#808080',
      authoredMaterials: [
        { name: 'base', color: '#808080' },
        { name: 'paint_link1_0_1', color: '#007aff' },
      ],
      meshMaterialGroups: [{ meshKey: '0', start: 0, count: 6, materialIndex: 1 }],
    };
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;

    await renderGeometryEditor(root, link, () => {}, robot);

    assert.ok(container.textContent?.includes('#808080'));
    assert.ok(container.textContent?.includes('#007aff'));
    const inputValues = Array.from(container.querySelectorAll('input')).map((input) =>
      (input as HTMLInputElement).value.trim().toLowerCase(),
    );
    assert.ok(inputValues.includes('#808080'));
    assert.ok(inputValues.includes('#007aff'));
    assert.equal(container.querySelector('input[type="color"][aria-label="Color"]'), null);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor coalesces authored material color drag updates before committing', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createMultiMaterialMeshLink();
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;
    const updates: UrdfLink[] = [];

    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
    );

    const bodyColorInput = container.querySelector(
      'input[type="color"][aria-label="Color body"]',
    ) as HTMLInputElement | null;
    assert.ok(bodyColorInput, 'expected a dedicated color picker for the body material');
    if (!bodyColorInput) {
      assert.fail('expected a dedicated color picker for the body material');
    }

    await act(async () => {
      dispatchReactChange(bodyColorInput, '#c0ffee');
      dispatchReactChange(bodyColorInput, '#ff6c0a');
      dispatchReactChange(bodyColorInput, '#007aff');
      assert.equal(updates.length, 0);
      await new Promise((resolve) => setTimeout(resolve, 80));
    });

    assert.equal(updates.length, 1);
    assert.equal(updates[0]?.visual.authoredMaterials?.[0]?.color, '#007aff');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor lets users edit each authored material color for multi-material mesh visuals', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createMultiMaterialMeshLink();
    const updates: UrdfLink[] = [];
    const rerenderEditor = async (nextLink: UrdfLink) => {
      const rerenderedRobot = createRobot(nextLink);
      rerenderedRobot.selection.objectIndex = 0;
      await renderGeometryEditor(
        root,
        nextLink,
        (updatedLink) => {
          updates.push(updatedLink);
        },
        rerenderedRobot,
      );
    };

    await rerenderEditor(link);

    assert.ok(container.textContent?.includes('Multiple Materials'));
    assert.ok(container.textContent?.includes('body'));
    assert.ok(container.textContent?.includes('trim'));
    assert.ok(container.textContent?.includes('fastener'));
    const inputValues = Array.from(container.querySelectorAll('input')).map((input) =>
      (input as HTMLInputElement).value.trim().toLowerCase(),
    );
    assert.ok(inputValues.includes('#bebebe'));
    assert.ok(inputValues.includes('#ffffff'));
    assert.ok(inputValues.includes('#000000'));
    assert.ok(
      container.textContent?.includes(
        'This visual uses multiple authored materials. Base texture editing is read-only here.',
      ),
    );
    assert.equal(container.querySelector('input[type="color"][aria-label="Color"]'), null);
    const bodyColorInput = container.querySelector(
      'input[type="color"][aria-label="Color body"]',
    ) as HTMLInputElement | null;
    assert.ok(bodyColorInput, 'expected a dedicated color picker for the body material');
    if (!bodyColorInput) {
      assert.fail('expected a dedicated color picker for the body material');
    }

    await act(async () => {
      dispatchReactChange(bodyColorInput, '#c0ffee');
      await new Promise((resolve) => setTimeout(resolve, 80));
    });

    let nextLink = updates.at(-1);
    assert.ok(nextLink, 'editing a material slot should emit an updated link');
    assert.equal(nextLink.visual.authoredMaterials?.[0]?.color, '#c0ffee');
    assert.equal(nextLink.visual.authoredMaterials?.[1]?.color, '#ffffff');
    assert.equal(nextLink.visual.authoredMaterials?.[2]?.color, '#000000');

    await rerenderEditor(nextLink);

    const lighterToneButton = container.querySelector(
      'button[title="Lighter body 7%"]',
    ) as HTMLButtonElement | null;
    assert.ok(lighterToneButton, 'expected tone nudges for each authored material slot');
    if (!lighterToneButton) {
      assert.fail('expected tone nudges for each authored material slot');
    }

    await clickElement(lighterToneButton);

    nextLink = updates.at(-1);
    assert.ok(nextLink, 'clicking a tone nudge should emit an updated link');
    assert.notEqual(nextLink.visual.authoredMaterials?.[0]?.color, '#c0ffee');

    await rerenderEditor(nextLink);

    const presetSwatch = container.querySelector(
      'button[title="body #ff6c0a"]',
    ) as HTMLButtonElement | null;
    assert.ok(presetSwatch, 'expected quick preset swatches for the body material');
    if (!presetSwatch) {
      assert.fail('expected quick preset swatches for the body material');
    }

    await clickElement(presetSwatch);

    nextLink = updates.at(-1);
    assert.ok(nextLink, 'clicking a preset swatch should emit an updated link');
    assert.equal(nextLink.visual.authoredMaterials?.[0]?.color, '#ff6c0a');

    await rerenderEditor(nextLink);

    const recentColorButton = container.querySelector(
      'button[title="Recent #c0ffee"]',
    ) as HTMLButtonElement | null;
    assert.ok(recentColorButton, 'expected recent color shortcuts for authored materials');
    if (!recentColorButton) {
      assert.fail('expected recent color shortcuts for authored materials');
    }

    await clickElement(recentColorButton);

    nextLink = updates.at(-1);
    assert.ok(nextLink, 'clicking a recent color should emit an updated link');
    assert.equal(nextLink.visual.authoredMaterials?.[0]?.color, '#c0ffee');

    await rerenderEditor(nextLink);

    const resetButton = container.querySelector(
      'button[title="Reset body"]',
    ) as HTMLButtonElement | null;
    assert.ok(resetButton, 'expected a reset action for each authored material slot');
    if (!resetButton) {
      assert.fail('expected a reset action for each authored material slot');
    }

    await clickElement(resetButton);

    nextLink = updates.at(-1);
    assert.ok(nextLink, 'resetting a material slot should emit an updated link');
    assert.equal(nextLink.visual.authoredMaterials?.[0]?.color, '#bebebe');
    assert.equal(
      Array.from(container.querySelectorAll('button')).some((button) =>
        button.textContent?.includes('Upload Image'),
      ),
      false,
    );
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor previews the primary visual legacy texture before promoting edits into authored materials', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;
    robot.materials = {
      base_link: {
        texture: 'textures/legacy.png',
      },
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'visual',
      {
        assets: {
          'textures/legacy.png': 'blob:legacy-texture',
          'textures/updated.png': 'blob:updated-texture',
        },
      },
    );

    assert.ok(container.textContent?.includes('textures/legacy.png'));

    const nextTextureButton = container.querySelector('[title="textures/updated.png"]');
    assert.ok(nextTextureButton, 'updated texture asset should render');
    await clickElement(nextTextureButton);

    assert.equal(
      updates.length,
      0,
      'single-clicking a texture should stay in preview mode without committing',
    );
    assert.ok(
      container.querySelector('img[src="blob:updated-texture"]'),
      'preview mode should render the selected texture image',
    );

    const applyButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === 'Apply',
    );
    assert.ok(applyButton, 'preview mode should expose an apply action');
    await clickElement(applyButton);

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'texture selection should emit an updated link');
    assert.equal(nextLink.visual.authoredMaterials?.[0]?.texture, 'textures/updated.png');
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor keeps showing the applied texture image inside the material properties', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    link.visual = {
      ...link.visual,
      authoredMaterials: [{ texture: 'textures/applied.png' }],
    };
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;

    await renderGeometryEditor(root, link, () => {}, robot, 'visual', {
      assets: {
        'textures/applied.png': 'blob:applied-texture',
      },
    });

    assert.ok(
      container.querySelector('img[src="blob:applied-texture"]'),
      'applied textures should continue rendering their preview image in the material properties',
    );
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor deletes texture library assets and clears the applied visual texture', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    link.visual = {
      ...link.visual,
      authoredMaterials: [{ color: '#00ff00', texture: 'textures/applied.png' }],
    };
    const robot = createRobot(link);
    robot.selection.objectIndex = 0;

    const updates: UrdfLink[] = [];
    const deletedAssets: string[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'visual',
      {
        assets: {
          'textures/applied.png': 'blob:applied-texture',
        },
        onDeleteAsset: (path) => {
          deletedAssets.push(path);
        },
      },
    );

    const deleteButton = container.querySelector(
      `button[aria-label="${translations.en.removeFromLibrary}: applied.png"]`,
    );
    assert.ok(deleteButton, 'texture library item should expose a delete button');
    await clickElement(deleteButton);

    assert.deepEqual(deletedAssets, ['textures/applied.png']);
    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'deleting the applied texture should emit an updated link');
    assert.deepEqual(nextLink.visual.authoredMaterials, [{ color: '#00ff00' }]);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor preserves the effective legacy link material color when promoting a texture into authored materials', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    link.visual = {
      ...link.visual,
    };
    Reflect.deleteProperty(link.visual, 'color');

    const robot = createRobot(link);
    robot.selection.objectIndex = 0;
    robot.materials = {
      base_link: {
        color: '#b2b2b2',
        texture: 'textures/legacy.png',
      },
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'visual',
      {
        assets: {
          'textures/legacy.png': 'blob:legacy-texture',
          'textures/updated.png': 'blob:updated-texture',
        },
      },
    );

    const nextTextureButton = container.querySelector('[title="textures/updated.png"]');
    assert.ok(nextTextureButton, 'updated texture asset should render');
    await clickElement(nextTextureButton);

    const applyButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent?.trim() === 'Apply',
    );
    assert.ok(applyButton, 'preview mode should expose an apply action');
    await clickElement(applyButton);

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'texture selection should emit an updated link');
    assert.deepEqual(nextLink.visual.authoredMaterials?.[0], {
      color: '#b2b2b2',
      texture: 'textures/updated.png',
    });
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor keeps secondary visual textures independent from the link-level legacy fallback', async () => {
  const { dom, container, root } = createComponentRoot();
  try {
    const link = createLink('#00ff00');
    const robot = createRobot(link);
    robot.materials = {
      base_link: {
        texture: 'textures/legacy.png',
      },
    };

    const updates: UrdfLink[] = [];
    await renderGeometryEditor(
      root,
      link,
      (nextLink) => {
        updates.push(nextLink);
      },
      robot,
      'visual',
      {
        assets: {
          'textures/legacy.png': 'blob:legacy-texture',
          'textures/secondary.png': 'blob:secondary-texture',
        },
      },
    );

    assert.ok(!container.textContent?.includes('textures/legacy.png'));

    const secondaryTextureButton = container.querySelector('[title="textures/secondary.png"]');
    assert.ok(secondaryTextureButton, 'secondary texture asset should render');
    await doubleClickElement(secondaryTextureButton);

    const nextLink = updates.at(-1);
    assert.ok(nextLink, 'secondary texture selection should emit an updated link');
    assert.equal(
      nextLink.visualBodies?.[0]?.authoredMaterials?.[0]?.texture,
      'textures/secondary.png',
    );
    assert.equal(nextLink.visual.authoredMaterials, undefined);
  } finally {
    await destroyComponentRoot(dom, root);
  }
});

test('GeometryEditor forwards sourceFilePath to mesh analysis worker requests', async () => {
  const originalWorker = globalThis.Worker;
  const fakeWorker = new FakeWorker();

  Object.defineProperty(globalThis, 'Worker', {
    configurable: true,
    writable: true,
    value: class {
      constructor() {
        return fakeWorker as unknown as Worker;
      }
    },
  });

  const { dom, container, root } = createComponentRoot();

  try {
    const link = createCollisionMeshStemReferenceLink();
    const robot = createRobot(link);
    robot.selection = {
      type: 'link',
      id: link.id,
      subType: 'collision',
      objectIndex: 1,
    };

    await renderGeometryEditor(root, link, () => {}, robot, 'collision', {
      sourceFilePath: 'unitree_model/B2/usd/b2.viewer_roundtrip.usd',
    });

    const typeSelect = container.querySelector('select');
    assert.ok(typeSelect, 'geometry type select should exist');

    await act(async () => {
      dispatchReactSelectChange(typeSelect as HTMLSelectElement, GeometryType.CYLINDER);
      await new Promise<void>((resolve) => {
        dom.window.requestAnimationFrame(() => resolve());
      });
    });

    await waitForWorkerPost(dom, fakeWorker);

    const workerRequest = fakeWorker.postedMessages.find(
      (message) =>
        (message as { tasks?: Array<{ meshPath?: string }> }).tasks?.[0]?.meshPath ===
        'meshes/forearm_visual.dae',
    ) as
      | {
          tasks: Array<{ sourceFilePath?: string }>;
        }
      | undefined;
    assert.ok(workerRequest, 'expected a mesh analysis request for the matched visual mesh');
    assert.equal(
      workerRequest.tasks[0]?.sourceFilePath,
      'unitree_model/B2/usd/b2.viewer_roundtrip.usd',
    );

    emitMeshAnalysisResult(fakeWorker);
    await act(async () => {
      await Promise.resolve();
    });
  } finally {
    Object.defineProperty(globalThis, 'Worker', {
      configurable: true,
      writable: true,
      value: originalWorker,
    });
    await destroyComponentRoot(dom, root);
  }
});

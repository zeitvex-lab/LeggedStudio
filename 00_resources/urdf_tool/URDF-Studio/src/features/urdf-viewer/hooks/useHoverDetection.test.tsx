import assert from 'node:assert/strict';
import test from 'node:test';

import React, { act, useMemo, useRef } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import * as THREE from 'three';
import { context as r3fContext } from '@react-three/fiber';
import { create } from 'zustand';

import { useHoverDetection, type UseHoverDetectionOptions } from './useHoverDetection.ts';

function installDom() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', {
    url: 'http://localhost/?regressionDebug=1',
    pretendToBeVisual: true,
  });

  (globalThis as { window?: Window }).window = dom.window as unknown as Window;
  (globalThis as { document?: Document }).document = dom.window.document;
  Object.defineProperty(globalThis, 'navigator', {
    value: dom.window.navigator,
    configurable: true,
  });
  (globalThis as { HTMLElement?: typeof HTMLElement }).HTMLElement = dom.window.HTMLElement;
  (globalThis as { HTMLCanvasElement?: typeof HTMLCanvasElement }).HTMLCanvasElement =
    dom.window.HTMLCanvasElement;
  (globalThis as { Event?: typeof Event }).Event = dom.window.Event;
  (globalThis as { requestAnimationFrame?: typeof requestAnimationFrame }).requestAnimationFrame =
    dom.window.requestAnimationFrame.bind(dom.window);
  (globalThis as { cancelAnimationFrame?: typeof cancelAnimationFrame }).cancelAnimationFrame =
    dom.window.cancelAnimationFrame.bind(dom.window);
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

  return dom;
}

function createComponentRoot() {
  const dom = installDom();
  const container = dom.window.document.getElementById('root');
  assert.ok(container, 'root container should exist');

  const root = createRoot(container);
  return { dom, root };
}

function createRobotFixture() {
  const robot = new THREE.Group() as THREE.Group & {
    links?: Record<string, THREE.Object3D>;
  };
  robot.name = 'hover-test-robot';

  const link = new THREE.Group() as THREE.Group & { isURDFLink?: boolean };
  link.name = 'base_link';
  link.isURDFLink = true;

  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(1, 1, 1),
    new THREE.MeshBasicMaterial({ color: 0x888888 }),
  );
  mesh.name = 'base_visual';
  mesh.userData.parentLinkName = 'base_link';
  mesh.userData.geometryRole = 'visual';
  mesh.userData.isVisualMesh = true;
  mesh.userData.objectIndex = 0;

  link.add(mesh);
  robot.add(link);
  robot.links = { base_link: link };
  robot.updateMatrixWorld(true);

  return { robot, mesh };
}

function createCanvas(dom: JSDOM) {
  const canvas = dom.window.document.createElement('canvas');
  Object.defineProperties(canvas, {
    clientWidth: { value: 200, configurable: true },
    clientHeight: { value: 200, configurable: true },
  });
  canvas.getBoundingClientRect = () =>
    ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      right: 200,
      bottom: 200,
      width: 200,
      height: 200,
      toJSON: () => {},
    }) as DOMRect;
  return canvas;
}

type FrameRef = {
  current: (state?: unknown, delta?: number, frame?: unknown) => void;
};

function createR3fStore({
  camera,
  canvas,
  scene,
  frameRefs,
}: {
  camera: THREE.Camera;
  canvas: HTMLCanvasElement;
  scene: THREE.Scene;
  frameRefs: FrameRef[];
}) {
  return create(() => ({
    camera,
    gl: {
      domElement: canvas,
    },
    invalidate: () => {},
    internal: {
      subscribe: (ref: FrameRef) => {
        frameRefs.push(ref);
        return () => {
          const index = frameRefs.indexOf(ref);
          if (index >= 0) {
            frameRefs.splice(index, 1);
          }
        };
      },
    },
    scene,
  }));
}

function HoverDetectionProbe({
  linkMeshMap,
  onHover,
  robot,
}: {
  linkMeshMap: Map<string, THREE.Mesh[]>;
  onHover: NonNullable<UseHoverDetectionOptions['onHover']>;
  robot: THREE.Object3D;
}) {
  const mouseRef = useRef(new THREE.Vector2(0, 0));
  const raycasterRef = useRef(new THREE.Raycaster());
  const hoveredLinkRef = useRef<string | null>(null);
  const isDraggingJoint = useRef(false);
  const needsRaycastRef = useRef(true);
  const linkMeshMapRef = useRef(linkMeshMap);
  const emptyRecord = useMemo(() => ({}), []);

  useHoverDetection({
    robot,
    robotVersion: 1,
    toolMode: 'select',
    hoverSelectionEnabled: true,
    mode: 'editor',
    showCollision: false,
    showVisual: true,
    showCollisionAlwaysOnTop: false,
    interactionLayerPriority: [],
    selection: { type: null, id: null },
    onHover,
    linkMeshMapRef,
    robotLinks: emptyRecord,
    robotJoints: emptyRecord,
    mouseRef,
    raycasterRef,
    hoveredLinkRef,
    isDraggingJoint,
    needsRaycastRef,
    rayIntersectsBoundingBox: () => true,
    highlightGeometry: () => {},
  });

  return null;
}

async function renderHarness({
  frameRefs,
  onHover,
  root,
  r3fStore,
  robot,
  linkMeshMap,
}: {
  frameRefs: FrameRef[];
  onHover: React.ComponentProps<typeof HoverDetectionProbe>['onHover'];
  root: Root;
  r3fStore: ReturnType<typeof createR3fStore>;
  robot: THREE.Object3D;
  linkMeshMap: Map<string, THREE.Mesh[]>;
}) {
  await act(async () => {
    root.render(
      <r3fContext.Provider value={r3fStore as unknown as React.ContextType<typeof r3fContext>}>
        <HoverDetectionProbe linkMeshMap={linkMeshMap} onHover={onHover} robot={robot} />
      </r3fContext.Provider>,
    );
  });

  assert.ok(frameRefs.length > 0, 'hover frame callback should subscribe');
}

test('rerendering hover detection does not clear an unchanged external hover', async () => {
  const { dom, root } = createComponentRoot();
  const { robot, mesh } = createRobotFixture();
  const linkMeshMap = new Map<string, THREE.Mesh[]>([['base_link:visual', [mesh]]]);
  const scene = new THREE.Scene();
  scene.add(robot);

  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 0, 4);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const frameRefs: FrameRef[] = [];
  const r3fStore = createR3fStore({
    camera,
    canvas: createCanvas(dom),
    frameRefs,
    scene,
  });
  const hoverEvents: Array<{
    type: 'link' | 'joint' | 'tendon' | null;
    id: string | null;
    subType?: 'visual' | 'collision';
  }> = [];
  const onHover = (
    type: 'link' | 'joint' | 'tendon' | null,
    id: string | null,
    subType?: 'visual' | 'collision',
  ) => {
    hoverEvents.push({ type, id, subType });
  };

  await renderHarness({ frameRefs, onHover, root, r3fStore, robot, linkMeshMap });

  await act(async () => {
    frameRefs.forEach((entry) => entry.current(r3fStore.getState(), 0));
  });

  assert.deepEqual(hoverEvents.at(-1), {
    type: 'link',
    id: 'base_link',
    subType: 'visual',
  });

  hoverEvents.length = 0;

  await renderHarness({ frameRefs, onHover, root, r3fStore, robot, linkMeshMap });

  assert.deepEqual(hoverEvents, []);

  await act(async () => {
    root.unmount();
  });
  dom.window.close();
});

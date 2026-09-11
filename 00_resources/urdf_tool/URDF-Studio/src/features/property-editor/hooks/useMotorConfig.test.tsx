import test from 'node:test';
import assert from 'node:assert/strict';

import React from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';

import type { MotorSpec } from '@/types';
import { useMotorConfig } from './useMotorConfig.ts';

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
  const originalMutationObserver = globalThis.MutationObserver;
  const originalRequestAnimationFrame = globalThis.requestAnimationFrame;
  const originalCancelAnimationFrame = globalThis.cancelAnimationFrame;

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
  Object.defineProperty(globalThis, 'MutationObserver', {
    configurable: true,
    writable: true,
    value: dom.window.MutationObserver,
  });
  Object.defineProperty(globalThis, 'requestAnimationFrame', {
    configurable: true,
    writable: true,
    value: (callback: FrameRequestCallback) => setTimeout(() => callback(Date.now()), 0),
  });
  Object.defineProperty(globalThis, 'cancelAnimationFrame', {
    configurable: true,
    writable: true,
    value: (handle: number) => clearTimeout(handle),
  });

  return {
    restore() {
      dom.window.close();
      restoreGlobalProperty('window', originalWindow);
      restoreGlobalProperty('document', originalDocument);
      restoreGlobalProperty('navigator', originalNavigator);
      restoreGlobalProperty('HTMLElement', originalHTMLElement);
      restoreGlobalProperty('SVGElement', originalSVGElement);
      restoreGlobalProperty('Node', originalNode);
      restoreGlobalProperty('MutationObserver', originalMutationObserver);
      restoreGlobalProperty('requestAnimationFrame', originalRequestAnimationFrame);
      restoreGlobalProperty('cancelAnimationFrame', originalCancelAnimationFrame);
    },
  };
}

function renderHook(options: Parameters<typeof useMotorConfig>[0]) {
  let hookValue: ReturnType<typeof useMotorConfig> | null = null as ReturnType<typeof useMotorConfig> | null;
  const container = document.createElement('div');
  document.body.appendChild(container);

  function Probe() {
    hookValue = useMotorConfig(options);
    return null;
  }

  const root = createRoot(container);
  flushSync(() => {
    root.render(React.createElement(Probe));
  });

  assert.ok(hookValue, 'hook should render');

  return {
    get hook() {
      assert.ok(hookValue, 'hook should stay mounted');
      return hookValue;
    },
    cleanup() {
      flushSync(() => {
        root.unmount();
      });
      if (container.parentNode) {
        container.parentNode.removeChild(container);
      }
    },
  };
}

function waitForReactToSettle() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

test('useMotorConfig clears hidden hardware metadata when motor source becomes none', async () => {
  const domEnvironment = installDomEnvironment();
  const updates: Array<{ type: 'link' | 'joint'; id: string; data: unknown }> = [];
  const motorLibrary: Record<string, MotorSpec[]> = {
    Unitree: [{ name: 'Go2-H1', armature: 0.18, velocity: 9.5, effort: 12 }],
  };
  const rendered = renderHook({
    motorLibrary,
    data: {
      hardware: {
        brand: 'CustomBrand',
        motorType: 'custom_motor',
        armature: 0.42,
        motorId: 'm-7',
        motorDirection: -1,
        hardwareInterface: 'position',
      },
      limit: {
        lower: -1.2,
        upper: 1.4,
        velocity: 5.6,
        effort: 3.9,
      },
    },
    selectionId: 'joint_1',
    onUpdate(type, id, data) {
      updates.push({ type, id, data });
    },
  });

  try {
    flushSync(() => {
      rendered.hook.handleSourceChange('None');
    });

    assert.equal(updates.length, 1);
    assert.deepEqual(updates[0], {
      type: 'joint',
      id: 'joint_1',
      data: {
        hardware: {
          brand: '',
          motorType: 'None',
          armature: 0,
          motorId: '',
          motorDirection: 1,
          hardwareInterface: undefined,
        },
        limit: {
          lower: -1.2,
          upper: 1.4,
          velocity: 5.6,
          effort: 3.9,
        },
      },
    });
  } finally {
    rendered.cleanup();
    await waitForReactToSettle();
    await waitForReactToSettle();
    domEnvironment.restore();
  }
});

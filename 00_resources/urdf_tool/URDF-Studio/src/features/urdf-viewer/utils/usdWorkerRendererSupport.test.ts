import test from 'node:test';
import assert from 'node:assert/strict';

import {
  supportsUsdWorkerRenderer,
} from './usdWorkerRendererSupport.ts';

test('supportsUsdWorkerRenderer requires offscreen transfer support and cross-origin isolation', () => {
  const workerStub = function WorkerStub() {};
  const offscreenCanvasStub = function OffscreenCanvasStub() {};
  const supportedScope = {
    Worker: workerStub,
    OffscreenCanvas: offscreenCanvasStub,
    HTMLCanvasElement: {
      prototype: {
        transferControlToOffscreen() {
          return {} as OffscreenCanvas;
        },
      },
    },
    crossOriginIsolated: true,
  } as unknown as typeof globalThis;

  const unsupportedScope = {
    Worker: workerStub,
    OffscreenCanvas: offscreenCanvasStub,
    HTMLCanvasElement: { prototype: {} },
    crossOriginIsolated: false,
  } as unknown as typeof globalThis;

  assert.equal(supportsUsdWorkerRenderer(supportedScope), true);
  assert.equal(supportsUsdWorkerRenderer(unsupportedScope), false);
});

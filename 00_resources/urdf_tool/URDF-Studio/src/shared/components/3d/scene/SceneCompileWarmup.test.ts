import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';

import {
  isSceneCompileWarmupBlocked,
  warmupSceneCompile,
} from './SceneCompileWarmup.ts';

test('warmupSceneCompile prefers sync compilation to avoid the async-poll race', async () => {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  let asyncCalls = 0;
  let syncCalls = 0;

  const renderer = {
    async compileAsync(sceneArg: THREE.Object3D, cameraArg: THREE.Camera) {
      asyncCalls += 1;
      assert.equal(sceneArg, scene);
      assert.equal(cameraArg, camera);
      return sceneArg;
    },
    compile() {
      syncCalls += 1;
      return new Set();
    },
  };

  const mode = await warmupSceneCompile(renderer, scene, camera);

  // Sync compile wins even when compileAsync is available: compileAsync's
  // readiness poll races with material disposal on rapid file switches.
  assert.equal(mode, 'sync');
  assert.equal(syncCalls, 1);
  assert.equal(asyncCalls, 0);
});

test('warmupSceneCompile falls back to async when sync compile is unavailable', async () => {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  let asyncCalls = 0;

  const renderer = {
    async compileAsync(sceneArg: THREE.Object3D, cameraArg: THREE.Camera) {
      asyncCalls += 1;
      assert.equal(sceneArg, scene);
      assert.equal(cameraArg, camera);
      return sceneArg;
    },
  };

  const mode = await warmupSceneCompile(renderer, scene, camera);

  assert.equal(mode, 'async');
  assert.equal(asyncCalls, 1);
});

test('warmupSceneCompile falls back to sync compilation', async () => {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  let syncCalls = 0;

  const renderer = {
    compile(sceneArg: THREE.Object3D, cameraArg: THREE.Camera) {
      syncCalls += 1;
      assert.equal(sceneArg, scene);
      assert.equal(cameraArg, camera);
      return new Set();
    },
  };

  const mode = await warmupSceneCompile(renderer, scene, camera);

  assert.equal(mode, 'sync');
  assert.equal(syncCalls, 1);
});

test('isSceneCompileWarmupBlocked reports lost WebGL contexts', () => {
  assert.equal(isSceneCompileWarmupBlocked({
    getContext: () => ({
      isContextLost: () => true,
    } as unknown as WebGLRenderingContext),
  }), true);

  assert.equal(isSceneCompileWarmupBlocked({
    getContext: () => ({
      isContextLost: () => false,
    } as unknown as WebGLRenderingContext),
  }), false);
});

test('isSceneCompileWarmupBlocked skips software renderers', () => {
  const debugRendererInfo = { UNMASKED_RENDERER_WEBGL: 0x9246 };
  const context = {
    RENDERER: 0x1f01,
    isContextLost: () => false,
    getExtension: (name: string) => (name === 'WEBGL_debug_renderer_info' ? debugRendererInfo : null),
    getParameter: (parameter: number) => {
      if (parameter === debugRendererInfo.UNMASKED_RENDERER_WEBGL) {
        return 'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)';
      }
      if (parameter === 0x1f01) {
        return 'WebKit WebGL';
      }
      return null;
    },
  } as unknown as WebGLRenderingContext;

  assert.equal(isSceneCompileWarmupBlocked({
    getContext: () => context,
  }), true);
});

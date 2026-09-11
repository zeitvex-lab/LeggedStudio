import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { BokehPass } from 'three/examples/jsm/postprocessing/BokehPass.js';
import { computeVisibleMeshBounds } from '@/shared/utils/threeBounds';
import type { SnapshotDofMode } from './snapshotConfig';
import { resolveSnapshotRenderTargetSamples } from './snapshotResolution';

export interface SnapshotDofSettings {
  focus: number;
  aperture: number;
  maxBlur: number;
}

const SNAPSHOT_DOF_SETTINGS: Record<
  Exclude<SnapshotDofMode, 'off'>,
  { aperture: number; maxBlur: number; focusOffset: number }
> = {
  subtle: {
    aperture: 0.008,
    maxBlur: 0.008,
    focusOffset: 0.12,
  },
  hero: {
    aperture: 0.014,
    maxBlur: 0.014,
    focusOffset: 0.24,
  },
};

function buildCanvasFromPixelBuffer(pixelBuffer: Uint8Array, width: number, height: number) {
  const captureCanvas = document.createElement('canvas');
  captureCanvas.width = width;
  captureCanvas.height = height;
  const ctx = captureCanvas.getContext('2d');

  if (!ctx) {
    return captureCanvas;
  }

  const imageData = ctx.createImageData(width, height);
  const rowStride = width * 4;

  for (let sourceRow = 0; sourceRow < height; sourceRow += 1) {
    const destinationRow = height - sourceRow - 1;
    const sourceOffset = sourceRow * rowStride;
    const destinationOffset = destinationRow * rowStride;
    imageData.data.set(
      pixelBuffer.subarray(sourceOffset, sourceOffset + rowStride),
      destinationOffset,
    );
  }

  ctx.putImageData(imageData, 0, 0);
  return captureCanvas;
}

export function resolveSnapshotDofSettings(
  scene: THREE.Scene,
  camera: THREE.Camera,
  dofMode: SnapshotDofMode,
): SnapshotDofSettings | null {
  if (dofMode === 'off' || !(camera instanceof THREE.PerspectiveCamera)) {
    return null;
  }

  const bounds = computeVisibleMeshBounds(scene);
  if (!bounds) {
    return null;
  }

  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  const preset = SNAPSHOT_DOF_SETTINGS[dofMode];
  const focus = Math.max(
    camera.near + 0.1,
    camera.position.distanceTo(sphere.center) - sphere.radius * preset.focusOffset,
  );

  return {
    focus,
    aperture: preset.aperture,
    maxBlur: preset.maxBlur,
  };
}

export function renderSceneWithDofToCanvas({
  gl,
  scene,
  camera,
  width,
  height,
  samples,
  settings,
}: {
  gl: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.Camera;
  width: number;
  height: number;
  samples?: number;
  settings: SnapshotDofSettings;
}) {
  const renderTarget = new THREE.WebGLRenderTarget(width, height, {
    type: THREE.UnsignedByteType,
    depthBuffer: true,
    stencilBuffer: false,
  });
  renderTarget.texture.colorSpace = THREE.SRGBColorSpace;
  renderTarget.samples = resolveSnapshotRenderTargetSamples({
    width,
    height,
    requestedSamples: samples ?? 0,
    maxSupportedSamples: gl.capabilities.maxSamples,
  });

  const composer = new EffectComposer(gl, renderTarget);
  composer.renderToScreen = false;
  composer.setPixelRatio(1);
  composer.setSize(width, height);

  const renderPass = new RenderPass(scene, camera);
  const bokehPass = new BokehPass(scene, camera, {
    focus: settings.focus,
    aperture: settings.aperture,
    maxblur: settings.maxBlur,
  });

  composer.addPass(renderPass);
  composer.addPass(bokehPass);
  composer.render();

  const pixelBuffer = new Uint8Array(width * height * 4);
  gl.readRenderTargetPixels(composer.readBuffer, 0, 0, width, height, pixelBuffer);

  bokehPass.dispose();
  composer.dispose();
  renderTarget.dispose();

  return buildCanvasFromPixelBuffer(pixelBuffer, width, height);
}

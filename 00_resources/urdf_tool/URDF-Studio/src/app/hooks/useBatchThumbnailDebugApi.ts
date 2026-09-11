import { useEffect, type RefObject } from 'react';
import type { RootState } from '@react-three/fiber';
import * as THREE from 'three';

import {
  captureWorkspaceCameraSnapshot,
  type WorkspaceCameraSnapshot,
} from '@/shared/components/3d';
import type { SnapshotPreviewAction } from '@/shared/components/3d/scene/snapshotConfig';
import { logRegressionError } from '@/shared/debug/consoleDiagnostics';
import { isRegressionDebugEnabled } from '@/shared/debug/regressionDebugEnabled';

interface BatchThumbnailDebugApiParams {
  previewActionRef: RefObject<SnapshotPreviewAction | null>;
  viewerCanvasStateRef: RefObject<RootState | null>;
}

/** Exposes the snapshot-preview pipeline used by batch thumbnail automation. */
export function useBatchThumbnailDebugApi({
  previewActionRef,
  viewerCanvasStateRef,
}: BatchThumbnailDebugApiParams): void {
  useEffect(() => {
    if (typeof window === 'undefined' || !isRegressionDebugEnabled(window)) {
      return;
    }

    let disposed = false;
    let attachTimer: number | null = null;

    const blobToBase64 = (blob: Blob) =>
      new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onerror = () => reject(reader.error);
        reader.onloadend = () => {
          const result = reader.result;
          if (typeof result !== 'string') {
            reject(new Error('FileReader did not return a data URL'));
            return;
          }
          const comma = result.indexOf(',');
          resolve(comma >= 0 ? result.slice(comma + 1) : result);
        };
        reader.readAsDataURL(blob);
      });

    const attach = () => {
      if (disposed) {
        return;
      }
      const api = window.__URDF_STUDIO_DEBUG__;
      if (!api) {
        attachTimer = window.setTimeout(() => {
          attachTimer = null;
          attach();
        }, 100);
        return;
      }
      api.captureSnapshot = async (options) => {
        const action = previewActionRef.current;
        if (!action) {
          return { ok: false, base64: null, width: 0, height: 0, format: 'png' };
        }
        try {
          const result = await action(options);
          return {
            ok: true,
            base64: await blobToBase64(result.blob),
            width: result.width,
            height: result.height,
            format: result.options.imageFormat,
          };
        } catch (error) {
          logRegressionError('[AppLayout] captureSnapshot failed', error);
          return { ok: false, base64: null, width: 0, height: 0, format: 'png' };
        }
      };
      // Dolly the active camera toward the orbit target. Used by batch
      // thumbnail automation to tighten or loosen the auto-framed view before
      // capture. Reads the live R3F state (camera + controls.target) captured
      // by onCanvasCreated; OrbitControls has damping disabled, so a direct
      // position write survives until the off-screen capture clones the camera.
      api.setCameraZoom = (factor: number): { ok: boolean } => {
        const state = viewerCanvasStateRef.current;
        if (!state?.camera || !Number.isFinite(factor) || factor <= 0) {
          return { ok: false };
        }
        const controls = state.controls as { target?: THREE.Vector3 } | undefined;
        const target = controls?.target
          ? new THREE.Vector3(controls.target.x, controls.target.y, controls.target.z)
          : new THREE.Vector3(0, 0, 0);
        state.camera.position.lerp(target, 1 - 1 / factor);
        state.camera.updateMatrixWorld();
        state.invalidate?.();
        return { ok: true };
      };
      // Re-frame onto the unioned robot-mesh bounding box, skipping the flat
      // ground plane. Used before captureSnapshot for SDF (and other) assets
      // whose cameraFollowPrimary did not converge — without it the robot can
      // render off-frame and the thumbnail comes out blank.
      api.frameScene = (): {
        ok: boolean;
        meshCount?: number;
        center?: number[];
        size?: number[];
        camPos?: number[];
        cameraSnapshot?: WorkspaceCameraSnapshot | null;
      } => {
        const state = viewerCanvasStateRef.current;
        if (!state?.scene || !state.camera) {
          return { ok: false };
        }
        const box = new THREE.Box3();
        let robotMeshCount = 0;
        state.scene.traverse((obj: THREE.Object3D) => {
          const mesh = obj as THREE.Mesh;
          if (!mesh.isMesh || !mesh.geometry) {
            return;
          }
          mesh.updateMatrixWorld(true);
          const meshBox = new THREE.Box3().setFromObject(mesh);
          if (meshBox.isEmpty()) {
            return;
          }
          const size = new THREE.Vector3();
          meshBox.getSize(size);
          // Skip scene helpers (ground plane, shadow catcher, grid, gizmos) by
          // name first — GroundShadowPlane / ReferenceGrid / axes report huge
          // 20x20 footprints that would otherwise dwarf the robot bbox.
          const helperName = (mesh.name || (mesh.parent?.name ?? '') || '').toLowerCase();
          if (
            helperName.includes('ground') ||
            helperName.includes('grid') ||
            helperName.includes('shadow') ||
            helperName.includes('axes') ||
            helperName.includes('gizmo') ||
            helperName.includes('plane')
          ) {
            return;
          }
          const maxHorizontal = Math.max(size.x, size.z);
          // Fallback: drop any broad, relatively-thin slab (an unnamed ground).
          if (maxHorizontal > 1 && size.y < maxHorizontal * 0.1) {
            return;
          }
          box.union(meshBox);
          robotMeshCount += 1;
        });
        if (robotMeshCount === 0) {
          return { ok: false, meshCount: 0 };
        }
        const center = new THREE.Vector3();
        box.getCenter(center);
        const size = new THREE.Vector3();
        box.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        const camera = state.camera as THREE.PerspectiveCamera;
        const controls = state.controls as
          | { target?: THREE.Vector3; update?: () => void }
          | undefined;
        if (controls?.target) {
          controls.target.set(center.x, center.y, center.z);
          controls.update?.();
        }
        // Frame by the bounding sphere with an aspect-aware distance so the
        // whole bbox fits regardless of orientation. The old maxDim/tan(fov)
        // formula under-distance for flat models viewed at an oblique angle
        // (their projected footprint is larger than the bbox dimension), which
        // clipped them at the frame edge (e.g. iscas_museum). Mirrors the
        // bounding-sphere framing used by computeCameraFrame.
        const boundingSphere = new THREE.Sphere();
        box.getBoundingSphere(boundingSphere);
        const radius =
          Number.isFinite(boundingSphere.radius) && boundingSphere.radius > 0
            ? boundingSphere.radius
            : maxDim / 2 || 0.25;
        const verticalFov = camera.fov ? THREE.MathUtils.degToRad(camera.fov) : Math.PI / 4;
        const aspect = Number.isFinite(camera.aspect) && camera.aspect > 0 ? camera.aspect : 1;
        const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * aspect);
        const distance =
          Math.max(radius / Math.sin(verticalFov / 2), radius / Math.sin(horizontalFov / 2)) * 1.15;
        // Grow the far plane to contain the whole model at the framed distance.
        // The viewer's default far is calibrated for typical robots and is far
        // too small for large scenes (iscas_museum / ksql_airport /
        // sonoma_raceway), so most of the model ends up beyond it and gets
        // clipped away, leaving a blank / ground-only frame.
        if (Number.isFinite(distance) && distance + radius * 2 > camera.far) {
          camera.far = distance + radius * 2;
          camera.updateProjectionMatrix();
        }
        const dir = new THREE.Vector3();
        if (controls?.target) {
          dir.subVectors(camera.position, controls.target);
        }
        if (dir.lengthSq() === 0) {
          dir.set(0.7, 0.5, 1);
        }
        dir.normalize();
        camera.position.copy(center).addScaledVector(dir, distance);
        // OrbitControls.update() ran against the *previous* camera position, so
        // the cloned camera's quaternion may not actually face `center` after
        // we repositioned. Force a lookAt so the bbox center is the view axis.
        camera.lookAt(center);
        camera.updateMatrixWorld();
        state.invalidate?.();
        // Snapshot the workspace camera synchronously — in the same tick, before
        // any animation frame runs — so callers (batch thumbnail automation) can
        // pass it to captureSnapshot and lock this framing onto the off-screen
        // capture camera. Without it, cameraFollowPrimary's per-frame update
        // reverts frameScene during the capture warmup frames for SDF assets
        // whose auto-frame does not converge, leaving the robot off-frame.
        const glDomElement = state.gl?.domElement ?? null;
        const cameraSnapshot = captureWorkspaceCameraSnapshot(
          state,
          glDomElement?.parentElement ?? glDomElement,
        );
        return {
          ok: true,
          meshCount: robotMeshCount,
          center: [
            Number(center.x.toFixed(3)),
            Number(center.y.toFixed(3)),
            Number(center.z.toFixed(3)),
          ],
          size: [Number(size.x.toFixed(3)), Number(size.y.toFixed(3)), Number(size.z.toFixed(3))],
          camPos: [
            Number(camera.position.x.toFixed(3)),
            Number(camera.position.y.toFixed(3)),
            Number(camera.position.z.toFixed(3)),
          ],
          cameraSnapshot,
        };
      };
    };

    attach();

    return () => {
      disposed = true;
      if (attachTimer !== null) {
        window.clearTimeout(attachTimer);
        attachTimer = null;
      }
      const api = window.__URDF_STUDIO_DEBUG__;
      if (api) {
        delete api.captureSnapshot;
        delete api.setCameraZoom;
        delete api.frameScene;
      }
    };
  }, [previewActionRef, viewerCanvasStateRef]);
}

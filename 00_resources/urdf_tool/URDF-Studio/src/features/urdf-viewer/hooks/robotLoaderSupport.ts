import type { RefObject } from 'react';
import * as THREE from 'three';
import { normalizeLoadingProgress } from '@/shared/components/3d/loadingHudState';
import type { RobotData, UrdfJoint, UrdfLink } from '@/types';
import type { RobotLoadingPhase, ViewerDocumentLoadEvent, ViewerRobotSourceFormat } from '../types';

export const VIEWER_LOAD_YIELD_BUDGET_MS = 4;

export interface RobotLoadingProgress {
  phase: RobotLoadingPhase;
  progressMode?: ViewerDocumentLoadEvent['progressMode'];
  loadedCount?: number | null;
  totalCount?: number | null;
  progressPercent?: number | null;
}

export interface UseRobotLoaderOptions {
  urdfContent: string;
  assets: Record<string, string>;
  sourceFormat?: ViewerRobotSourceFormat;
  allowUrdfXmlFallback?: boolean;
  reloadToken?: number;
  initialRobot?: THREE.Object3D | null;
  showCollision: boolean;
  showVisual: boolean;
  showCollisionAlwaysOnTop?: boolean;
  isMeshPreview?: boolean;
  robotLinks?: Record<string, UrdfLink>;
  robotJoints?: Record<string, UrdfJoint>;
  robotInspectionContext?: RobotData['inspectionContext'];
  initialJointAngles?: Record<string, number>;
  sourceFilePath?: string;
  onRobotLoaded?: (robot: THREE.Object3D) => void;
  onDocumentLoadEvent?: (event: ViewerDocumentLoadEvent) => void;
  groundPlaneOffset?: number;
  showMjcfWorldLink?: boolean;
}

export interface UseRobotLoaderResult {
  robot: THREE.Object3D | null;
  error: string | null;
  isLoading: boolean;
  loadingProgress: RobotLoadingProgress | null;
  robotVersion: number;
  robotRef: RefObject<THREE.Object3D | null>;
  linkMeshMapRef: RefObject<Map<string, THREE.Mesh[]>>;
}

export interface PendingLoadingDispatch {
  event: ViewerDocumentLoadEvent;
  progress: RobotLoadingProgress | null;
}

export function preprocessURDFForLoader(content: string): string {
  // Remove <transmission> blocks to prevent urdf-loader from finding duplicate joints
  // which can overwrite valid joints with empty origins.
  return content.replace(/<transmission[\s\S]*?<\/transmission>/g, '');
}

export function waitForLoadingHudPaint(invalidate?: () => void): Promise<void> {
  invalidate?.();

  if (typeof window === 'undefined' || typeof window.requestAnimationFrame !== 'function') {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => resolve());
    });
  });
}

export function resolveRobotJoint(
  joints: Record<string, UrdfJoint> | null | undefined,
  jointNameOrId: string,
): UrdfJoint | undefined {
  if (!joints) {
    return undefined;
  }

  return (
    joints[jointNameOrId] ??
    Object.values(joints).find((joint) => joint.name === jointNameOrId)
  );
}

export function createAssetScopeKey(assets: Record<string, string>): string {
  const assetEntries = Object.entries(assets).sort(([leftPath], [rightPath]) =>
    leftPath.localeCompare(rightPath),
  );
  let hash = 0x811c9dc5;

  for (const [assetPath, assetUrl] of assetEntries) {
    const signature = `${assetPath}\u0000${assetUrl}`;
    for (let index = 0; index < signature.length; index += 1) {
      hash ^= signature.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
  }

  return `${assetEntries.length}:${(hash >>> 0).toString(36)}`;
}

export function normalizeExternalDocumentLoadEvent(
  event: ViewerDocumentLoadEvent,
): ViewerDocumentLoadEvent {
  if (event.status !== 'loading') {
    return event;
  }

  return normalizeLoadingProgress<ViewerDocumentLoadEvent>(event);
}

export function createLoadingDispatchKey(
  progress: RobotLoadingProgress | null,
  event: ViewerDocumentLoadEvent | null,
): string {
  return JSON.stringify({ progress, event });
}

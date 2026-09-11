import * as THREE from 'three';
import { applyVisualMeshShadowPolicy } from '@/core/utils/visualMeshShadowPolicy';

export function prepareUsdVisualMesh(mesh: THREE.Mesh): void {
  applyVisualMeshShadowPolicy(mesh);
  mesh.userData.__usdVisualMeshPrepared = true;
}

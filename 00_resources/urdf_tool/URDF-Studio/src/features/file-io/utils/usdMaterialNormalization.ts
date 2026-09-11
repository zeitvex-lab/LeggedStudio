import * as THREE from 'three';

import { createMatteMaterial } from '@/core/utils/materialFactory.ts';
import { disposeMaterial } from '@/shared/utils/three/dispose.ts';

export const createUsdBaseMaterial = (color?: string): THREE.MeshStandardMaterial => {
  const material = createMatteMaterial({
    color: color || '#808080',
    side: THREE.FrontSide,
    preserveExactColor: true,
  });
  material.userData = {
    ...(material.userData ?? {}),
    usdGeneratedBaseMaterial: true,
  };
  return material;
};

export const isUsdMeshObject = (value: unknown): value is THREE.Mesh => {
  return Boolean(
    value &&
    typeof value === 'object' &&
    (value as THREE.Mesh).isMesh &&
    'geometry' in (value as Record<string, unknown>),
  );
};

const isMeshStandardMaterial = (
  material: THREE.Material,
): material is THREE.MeshStandardMaterial => {
  return Boolean((material as THREE.MeshStandardMaterial).isMeshStandardMaterial);
};

const applyVertexColorMaterialState = (material: THREE.Material): void => {
  (material as { vertexColors?: boolean }).vertexColors = true;
  const materialColor = (material as { color?: THREE.Color }).color;
  if (materialColor?.isColor) {
    materialColor.set(0xffffff);
  }
  material.toneMapped = false;
  material.userData = {
    ...(material.userData ?? {}),
    usesVertexColors: true,
  };
  material.needsUpdate = true;
};

const convertUsdMaterialToStandard = (
  material: THREE.Material,
  fallbackColor: string | undefined,
  usesVertexColors: boolean,
): THREE.MeshStandardMaterial => {
  if (isMeshStandardMaterial(material)) {
    const cloned = material.clone();
    cloned.side = THREE.FrontSide;
    if (usesVertexColors) {
      applyVertexColorMaterialState(cloned);
    }
    cloned.needsUpdate = true;
    return cloned;
  }

  const nextMaterial = createUsdBaseMaterial(usesVertexColors ? '#ffffff' : fallbackColor);
  const source = material as THREE.MeshStandardMaterial & {
    color?: THREE.Color;
    map?: THREE.Texture | null;
  };

  if (source.color && !usesVertexColors) {
    nextMaterial.color.copy(source.color);
  }

  if (source.map) {
    nextMaterial.map = source.map;
  }

  if (source.color || source.map || material.name?.trim()) {
    delete nextMaterial.userData.usdGeneratedBaseMaterial;
  }

  nextMaterial.transparent = material.transparent || material.opacity < 1;
  nextMaterial.opacity = material.opacity ?? 1;
  nextMaterial.name = material.name;
  nextMaterial.side = THREE.FrontSide;
  if (usesVertexColors) {
    applyVertexColorMaterialState(nextMaterial);
  }
  nextMaterial.needsUpdate = true;

  disposeMaterial(material, false);
  return nextMaterial;
};

export const normalizeUsdRenderableMaterials = (
  object: THREE.Object3D,
  fallbackColor: string | undefined,
): void => {
  object.traverse((child) => {
    if (!isUsdMeshObject(child)) return;

    const usesVertexColors = Boolean(child.geometry.getAttribute('color'));
    if (Array.isArray(child.material)) {
      child.material = child.material.map((material) =>
        convertUsdMaterialToStandard(material, fallbackColor, usesVertexColors),
      );
      return;
    }

    if (!child.material) {
      child.material = createUsdBaseMaterial(fallbackColor);
      if (usesVertexColors) {
        applyVertexColorMaterialState(child.material);
      }
      return;
    }

    child.material = convertUsdMaterialToStandard(child.material, fallbackColor, usesVertexColors);
  });
};

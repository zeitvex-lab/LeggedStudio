/**
 * GeometryEditor - Visual/Collision geometry editing for a Link.
 * Handles geometry type selection, dimension editing, mesh selection,
 * origin/rotation, color, and auto-align.
 */
import React, { useState, useRef, useMemo, useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import type { UrdfVisual } from '@/types';
import { GeometryType } from '@/types';
import { useAssetsStore } from '@/store/assetsStore';
import { useCollisionTransformStore } from '@/store/collisionTransformStore';
import { useSelectionStore } from '@/store/selectionStore';
import {
  canEditGeometryBaseTexture,
  getVisualGeometryByObjectIndex,
  hasGeometryMeshMaterialGroups,
  resolveVisualMaterialOverride,
  updateVisualBaseTextureByObjectIndex,
  updateVisualGeometryByObjectIndex,
  getCollisionGeometryByObjectIndex,
  removeCollisionGeometryByObjectIndex,
  updateCollisionGeometryByObjectIndex,
} from '@/core/robot';
import {
  InputGroup,
  PROPERTY_EDITOR_SECTION_TITLE_CLASS,
} from './FormControls';

import { computeAutoAlign, convertGeometryType } from '../utils/geometryConversion';
import {
  getColorOpacityValue,
  mergeColorOpacityValue,
} from '../utils/colorInput';
import {
  clampMaterialOpacity,
  getUniqueAuthoredMaterialColors,
  normalizeMaterialColor,
  withAuthoredMaterialOpacity,
} from '../utils/geometryMaterial';
import type { MeshAnalysis, MeshClearanceObstacle } from '../utils/geometryConversion';
import { useGeometryMeshAnalysis } from '../utils/useGeometryMeshAnalysis';
import { buildColladaRootNormalizationHints } from '@/core/loaders/colladaRootNormalization';
import { TransformFields } from './TransformFields';
import { GeometryEditorHeader } from './GeometryEditorHeader';
import { GeometryDimensionsSection } from './GeometryDimensionsSection';
import { GeometryMeshLibraryPanel } from './GeometryMeshLibraryPanel';
import { VisualMaterialEditor } from './VisualMaterialEditor';
import type { GeometryEditorProps, GeometrySnapshotCache } from './GeometryEditor.types';
import {
  COLLISION_VISUAL_MESH_REFERENCE_TYPES,
  EDITABLE_GEOMETRY_TYPES,
  GEOMETRY_EDITOR_COMPACT_ACTIONS_WIDTH,
  GEOMETRY_EDITOR_RELAXED_FIT_VOLUME_WINDOW_RATIO,
  GEOMETRY_EDITOR_RELAXED_OVERLAP_ALLOWANCE_RATIO,
  MJCF_SPECIAL_GEOMETRY_TYPES,
} from './geometryEditorConstants';
import {
  createGeometrySnapshot,
  resolveCollisionVisualMeshReference,
  yieldToNextFrame,
} from './geometryEditorUtils';

export const GeometryEditor: React.FC<GeometryEditorProps> = ({
  componentId,
  data,
  robot,
  category,
  onUpdate,
  assets,
  onUploadAsset,
  onDeleteAsset,
  t,
  lang,
  isTabbed = false,
  showCollisionDeleteAction = true,
  sourceFilePath,
  onLinkNameChange,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textureFileInputRef = useRef<HTMLInputElement>(null);
  const [previewMeshPath, setPreviewMeshPath] = useState<string | null>(null);
  const [previewTexturePath, setPreviewTexturePath] = useState<string | null>(null);
  const geometryHeaderRowRef = useRef<HTMLDivElement>(null);
  const typeChangeRequestRef = useRef(0);
  const [geometryHeaderRowWidth, setGeometryHeaderRowWidth] = useState<number | null>(null);
  const setSelection = useSelectionStore((state) => state.setSelection);
  const removeAsset = useAssetsStore((state) => state.removeAsset);
  const pendingCollisionTransform = useCollisionTransformStore(
    (state) => state.pendingCollisionTransform,
  );

  const selectedCollisionObjectIndex =
    category === 'collision' &&
    robot.selection.type === 'link' &&
    robot.selection.id === data.id &&
    robot.selection.subType === 'collision'
      ? (robot.selection.objectIndex ?? 0)
      : 0;
  const selectedVisualObjectIndex =
    category === 'visual' &&
    robot.selection.type === 'link' &&
    robot.selection.id === data.id &&
    robot.selection.subType === 'visual'
      ? (robot.selection.objectIndex ?? 0)
      : 0;
  const selectedCollisionGeometry =
    category === 'collision'
      ? getCollisionGeometryByObjectIndex(data, selectedCollisionObjectIndex)
      : null;
  const selectedVisualGeometry =
    category === 'visual' ? getVisualGeometryByObjectIndex(data, selectedVisualObjectIndex) : null;
  const geomData =
    category === 'collision'
      ? selectedCollisionGeometry?.geometry || data.collision
      : selectedVisualGeometry?.geometry || data.visual;
  const { meshAnalysisRef, resolveMeshAnalysisForGeometry } = useGeometryMeshAnalysis({
    assets,
    geometry: geomData,
    sourceFilePath,
  });
  const colladaRootNormalizationHints = useMemo(
    () => buildColladaRootNormalizationHints(robot.links),
    [robot.links],
  );
  const meshFiles = useMemo(
    () =>
      Object.keys(assets)
        .filter((filePath) => /\.(stl|msh|obj|dae|gltf|glb|ply|vtk)$/i.test(filePath))
        .sort((left, right) => left.localeCompare(right)),
    [assets],
  );
  const textureFiles = useMemo(
    () =>
      Object.keys(assets)
        .filter((filePath) => /\.(png|jpe?g|webp)$/i.test(filePath))
        .sort((left, right) => left.localeCompare(right)),
    [assets],
  );

  const isCompactGeometryActions =
    geometryHeaderRowWidth !== null &&
    geometryHeaderRowWidth < GEOMETRY_EDITOR_COMPACT_ACTIONS_WIDTH;
  const materialSourceLabel =
    geomData.materialSource === 'inline'
      ? t.materialSourceInline
      : geomData.materialSource === 'named'
        ? t.materialSourceNamed
        : geomData.materialSource === 'gazebo'
          ? t.materialSourceGazebo
          : null;
  const currentGeometryType = geomData.type || GeometryType.CYLINDER;
  const geometryNameValue = geomData.name?.trim() ?? '';
  const geometryTypeOptions =
    EDITABLE_GEOMETRY_TYPES.includes(currentGeometryType) ||
    currentGeometryType === GeometryType.NONE
      ? [...EDITABLE_GEOMETRY_TYPES, GeometryType.NONE]
      : [...EDITABLE_GEOMETRY_TYPES, currentGeometryType, GeometryType.NONE];
  const geometrySnapshotCacheRef = useRef<GeometrySnapshotCache>({});
  const snapshotKey =
    category === 'collision'
      ? `${data.id}:${category}:${selectedCollisionGeometry?.bodyIndex ?? 'primary'}`
      : `${data.id}:${category}:${selectedVisualGeometry?.bodyIndex ?? 'primary'}`;

  const authoredMaterialColors = useMemo(() => {
    return getUniqueAuthoredMaterialColors(geomData.authoredMaterials);
  }, [geomData.authoredMaterials]);
  const hasReadonlyAuthoredMaterialDisplay =
    category === 'visual' &&
    (!geomData.color ||
      hasGeometryMeshMaterialGroups(geomData) ||
      authoredMaterialColors.length > 1) &&
    authoredMaterialColors.length > 0;
  const authoredMaterialDisplayLabel = hasReadonlyAuthoredMaterialDisplay
    ? authoredMaterialColors.length === 1
      ? authoredMaterialColors[0]
      : `${t.multipleMaterials}: ${authoredMaterialColors.join(', ')}`
    : null;
  const isPrimaryVisualSelection =
    category === 'visual'
      ? selectedVisualGeometry
        ? selectedVisualGeometry.bodyIndex === null
        : selectedVisualObjectIndex === 0
      : false;
  const resolvedVisualMaterial =
    category === 'visual'
      ? resolveVisualMaterialOverride(robot, data, geomData, {
          isPrimaryVisual: isPrimaryVisualSelection,
        })
      : null;
  const effectiveTexturePath =
    category === 'visual' ? resolvedVisualMaterial?.texture?.trim() || '' : '';
  const displayedTexturePath = previewTexturePath || effectiveTexturePath;
  const displayedTextureAssetUrl = displayedTexturePath ? assets[displayedTexturePath] : null;
  const isTextureReadonly = category === 'visual' && !canEditGeometryBaseTexture(geomData);
  const effectiveColorValue =
    category === 'visual'
      ? resolvedVisualMaterial?.color?.trim() || geomData.color || '#ffffff'
      : geomData.color || '#ffffff';
  const effectiveOpacityValue =
    category === 'visual'
      ? clampMaterialOpacity(
          resolvedVisualMaterial?.opacity ??
            resolvedVisualMaterial?.colorRgba?.[3] ??
            getColorOpacityValue(effectiveColorValue, 1),
        )
      : clampMaterialOpacity(getColorOpacityValue(geomData.color, 1));
  const displayedOrigin = useMemo(() => {
    if (category !== 'collision' || !pendingCollisionTransform) {
      return geomData.origin;
    }

    if (pendingCollisionTransform.linkId !== data.id) {
      return geomData.origin;
    }

    if ((pendingCollisionTransform.objectIndex ?? 0) !== selectedCollisionObjectIndex) {
      return geomData.origin;
    }

    return {
      xyz: pendingCollisionTransform.position,
      rpy: pendingCollisionTransform.rotation,
    };
  }, [category, data.id, geomData.origin, pendingCollisionTransform, selectedCollisionObjectIndex]);

  const update = (newData: Partial<typeof geomData>) => {
    if (category === 'collision') {
      if (selectedCollisionGeometry) {
        onUpdate(updateCollisionGeometryByObjectIndex(data, selectedCollisionObjectIndex, newData));
        return;
      }

      onUpdate({
        ...data,
        collision: {
          ...data.collision,
          ...newData,
        },
      });
      return;
    }

    if (selectedVisualGeometry) {
      onUpdate(updateVisualGeometryByObjectIndex(data, selectedVisualObjectIndex, newData));
      return;
    }

    onUpdate({
      ...data,
      visual: {
        ...data.visual,
        ...newData,
      },
    });
  };

  useEffect(() => {
    const node = geometryHeaderRowRef.current;

    if (!node || typeof ResizeObserver === 'undefined') {
      return;
    }

    const updateWidth = () => {
      const nextWidth = Math.round(node.getBoundingClientRect().width);
      setGeometryHeaderRowWidth((previousWidth) =>
        previousWidth === nextWidth ? previousWidth : nextWidth,
      );
    };

    updateWidth();

    const observer = new ResizeObserver(() => {
      updateWidth();
    });

    observer.observe(node);

    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const currentType = geomData.type || GeometryType.CYLINDER;
    if (!geometrySnapshotCacheRef.current[snapshotKey]) {
      geometrySnapshotCacheRef.current[snapshotKey] = {};
    }
    geometrySnapshotCacheRef.current[snapshotKey][currentType] = createGeometrySnapshot(geomData);
  }, [geomData, snapshotKey]);

  useEffect(() => {
    setPreviewTexturePath(null);
  }, [category, data.id, selectedVisualObjectIndex]);

  const resolveCollisionClearanceContext = async (): Promise<{
    siblingGeometries?: UrdfVisual[];
    meshClearanceObstacles?: MeshClearanceObstacle[];
    overlapAllowanceRatio?: number;
    fitVolumeWindowRatio?: number;
  }> => {
    if (category !== 'collision') {
      return {};
    }

    return {
      overlapAllowanceRatio: GEOMETRY_EDITOR_RELAXED_OVERLAP_ALLOWANCE_RATIO,
      fitVolumeWindowRatio: GEOMETRY_EDITOR_RELAXED_FIT_VOLUME_WINDOW_RATIO,
    };
  };

  const handleApplyMesh = () => {
    if (previewMeshPath) {
      update({ meshPath: previewMeshPath });
      setPreviewMeshPath(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUploadAsset(e.target.files[0]);
    }
  };

  const applyVisualTexture = (texturePath: string | null | undefined) => {
    if (category !== 'visual') {
      return;
    }

    if (resolvedVisualMaterial?.source === 'legacy-link' && isPrimaryVisualSelection) {
      const nextTexture = String(texturePath || '').trim() || undefined;
      const nextColor = resolvedVisualMaterial.color?.trim() || undefined;
      const nextAuthoredMaterials =
        nextColor || nextTexture
          ? [
              {
                ...(nextColor ? { color: nextColor } : {}),
                ...(nextTexture ? { texture: nextTexture } : {}),
              },
            ]
          : undefined;

      if (selectedVisualGeometry) {
        onUpdate(
          updateVisualGeometryByObjectIndex(data, selectedVisualObjectIndex, {
            authoredMaterials: nextAuthoredMaterials,
          }),
        );
        return;
      }

      onUpdate({
        ...data,
        visual: {
          ...data.visual,
          authoredMaterials: nextAuthoredMaterials,
        },
      });
      return;
    }

    onUpdate(updateVisualBaseTextureByObjectIndex(data, selectedVisualObjectIndex, texturePath));
  };

  const handleApplyTexture = () => {
    if (!previewTexturePath) {
      return;
    }

    if (previewTexturePath === effectiveTexturePath) {
      setPreviewTexturePath(null);
      return;
    }

    applyVisualTexture(previewTexturePath);
    setPreviewTexturePath(null);
  };

  const handleTextureFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }

    onUploadAsset(file);
    setPreviewTexturePath(file.name);
    e.target.value = '';
  };

  const handleDeleteTextureAsset = (filePath: string) => {
    if (previewTexturePath === filePath) {
      setPreviewTexturePath(null);
    }
    if (effectiveTexturePath === filePath) {
      applyVisualTexture(undefined);
    }
    (onDeleteAsset ?? removeAsset)(filePath);
  };

  // Handle editing individual authored material colors
  const handleAuthoredMaterialColorChange = (index: number, newColor: string) => {
    const currentAuthoredMaterials = geomData.authoredMaterials || [];
    if (!currentAuthoredMaterials[index]) {
      return;
    }

    const nextAuthoredMaterials = [...currentAuthoredMaterials];
    nextAuthoredMaterials[index] = {
      ...nextAuthoredMaterials[index],
      color: newColor,
    };

    update({ authoredMaterials: nextAuthoredMaterials });
  };

  const handleAuthoredMaterialOpacityChange = (index: number, opacity: number) => {
    const currentAuthoredMaterials = geomData.authoredMaterials || [];
    const currentMaterial = currentAuthoredMaterials[index];
    if (!currentMaterial) {
      return;
    }

    const nextAuthoredMaterials = [...currentAuthoredMaterials];
    nextAuthoredMaterials[index] = withAuthoredMaterialOpacity(currentMaterial, opacity);

    update({ authoredMaterials: nextAuthoredMaterials });
  };

  const handleSingleMaterialColorChange = (newColor: string) => {
    const currentAuthoredMaterials = geomData.authoredMaterials || [];
    const hasSingleAuthoredMaterial =
      currentAuthoredMaterials.length === 1 || resolvedVisualMaterial?.source === 'authored';

    if (hasSingleAuthoredMaterial) {
      const currentMaterial = currentAuthoredMaterials[0] || {};
      update({
        authoredMaterials: [
          {
            ...currentMaterial,
            color: newColor,
          },
        ],
      });
      return;
    }

    update({ color: newColor });
  };

  const handleSingleMaterialOpacityChange = (opacity: number) => {
    if (category !== 'visual') {
      return;
    }

    const currentAuthoredMaterials = geomData.authoredMaterials || [];
    const currentMaterial = currentAuthoredMaterials[0] || {};
    const nextColor =
      currentMaterial.color ||
      resolvedVisualMaterial?.color ||
      geomData.color ||
      mergeColorOpacityValue('#ffffff', opacity);
    const nextTexture = currentMaterial.texture || resolvedVisualMaterial?.texture || undefined;
    const nextMaterial = withAuthoredMaterialOpacity(
      {
        ...currentMaterial,
        ...(nextColor ? { color: nextColor } : {}),
        ...(nextTexture ? { texture: nextTexture } : {}),
      },
      opacity,
    );

    update({ authoredMaterials: [nextMaterial] });
  };

  // Memoized auto-align calculation
  const autoAlignResult = useMemo(() => computeAutoAlign(robot, data.id), [robot.joints, data.id]);

  const handleAutoAlign = () => {
    if (!autoAlignResult) return;

    const currentDims = geomData.dimensions || { x: 0.05, y: 0.5, z: 0.05 };
    const newDims = { ...currentDims, y: autoAlignResult.dimensions.y };

    update({
      dimensions: newDims,
      origin: autoAlignResult.origin,
    });
  };

  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newType = e.currentTarget.value as GeometryType;
    const currentType = geomData.type || GeometryType.CYLINDER;
    if (newType === currentType) return;

    if (!geometrySnapshotCacheRef.current[snapshotKey]) {
      geometrySnapshotCacheRef.current[snapshotKey] = {};
    }
    const cacheByType = geometrySnapshotCacheRef.current[snapshotKey];
    cacheByType[currentType] = createGeometrySnapshot(geomData);

    const cachedTarget = cacheByType[newType];
    const representativeMeshColor =
      currentType === GeometryType.MESH && newType !== GeometryType.MESH
        ? meshAnalysisRef.current?.representativeColor
        : undefined;
    if (cachedTarget) {
      const shouldUseRepresentativeMeshColor =
        Boolean(representativeMeshColor) &&
        newType !== GeometryType.MESH &&
        (!cachedTarget.color ||
          normalizeMaterialColor(cachedTarget.color) === normalizeMaterialColor(geomData.color));

      update({
        type: newType,
        dimensions: cachedTarget.dimensions || geomData.dimensions,
        origin: cachedTarget.origin || geomData.origin,
        meshPath: newType === GeometryType.MESH ? cachedTarget.meshPath : undefined,
        assetRef: MJCF_SPECIAL_GEOMETRY_TYPES.has(newType) ? cachedTarget.assetRef : undefined,
        mjcfHfield: newType === GeometryType.HFIELD ? cachedTarget.mjcfHfield : undefined,
        color: shouldUseRepresentativeMeshColor
          ? representativeMeshColor
          : cachedTarget.color || geomData.color,
      });
      return;
    }

    const requestId = ++typeChangeRequestRef.current;

    void (async () => {
      await yieldToNextFrame();

      let conversionSourceGeometry = geomData;
      let meshAnalysis: MeshAnalysis | undefined;

      if (
        category === 'collision' &&
        (COLLISION_VISUAL_MESH_REFERENCE_TYPES.has(newType) || newType === GeometryType.MESH)
      ) {
        const visualMeshReference = resolveCollisionVisualMeshReference(
          data,
          selectedCollisionObjectIndex,
          geomData,
        );

        if (visualMeshReference) {
          if (newType === GeometryType.MESH) {
            conversionSourceGeometry = visualMeshReference;
          } else {
            const referenceMeshAnalysis = await resolveMeshAnalysisForGeometry(visualMeshReference);
            if (referenceMeshAnalysis) {
              conversionSourceGeometry = visualMeshReference;
              meshAnalysis = referenceMeshAnalysis;
            }
          }
        }
      }

      if (!meshAnalysis && currentType === GeometryType.MESH) {
        meshAnalysis = (await resolveMeshAnalysisForGeometry(geomData)) ?? undefined;
      }
      const resolvedRepresentativeMeshColor =
        currentType === GeometryType.MESH && newType !== GeometryType.MESH
          ? meshAnalysis?.representativeColor
          : undefined;
      const clearanceContext =
        newType !== GeometryType.MESH ? await resolveCollisionClearanceContext() : undefined;

      if (typeChangeRequestRef.current !== requestId) {
        return;
      }

      const converted =
        newType === GeometryType.MESH && conversionSourceGeometry.type === GeometryType.MESH
          ? {
              type: GeometryType.MESH,
              dimensions: conversionSourceGeometry.dimensions ?? { x: 1, y: 1, z: 1 },
              origin: conversionSourceGeometry.origin ?? {
                xyz: { x: 0, y: 0, z: 0 },
                rpy: { r: 0, p: 0, y: 0 },
              },
            }
          : convertGeometryType(conversionSourceGeometry, newType, meshAnalysis, clearanceContext);
      const nextGeom = {
        ...converted,
        meshPath:
          newType === GeometryType.MESH
            ? conversionSourceGeometry.type === GeometryType.MESH
              ? conversionSourceGeometry.meshPath
              : geomData.meshPath
            : undefined,
        assetRef: MJCF_SPECIAL_GEOMETRY_TYPES.has(newType) ? geomData.assetRef : undefined,
        mjcfHfield: newType === GeometryType.HFIELD ? geomData.mjcfHfield : undefined,
        color:
          newType === GeometryType.MESH
            ? geomData.color
            : resolvedRepresentativeMeshColor || geomData.color,
      };

      cacheByType[newType] = createGeometrySnapshot(nextGeom);
      update(nextGeom);
    })();
  };

  const handleDeleteCollision = () => {
    if (category !== 'collision') return;

    if (!selectedCollisionGeometry) {
      if (data.collision.type === GeometryType.NONE) return;
      onUpdate({
        ...data,
        collision: {
          ...data.collision,
          type: GeometryType.NONE,
          meshPath: undefined,
        },
      });
      setSelection({ entity: { type: 'link', componentId, entityId: data.id } });
      return;
    }

    const {
      link: nextLink,
      removed,
      nextObjectIndex,
    } = removeCollisionGeometryByObjectIndex(data, selectedCollisionObjectIndex);

    if (!removed) return;

    onUpdate(nextLink);
    if (nextObjectIndex === null) {
      setSelection({ entity: { type: 'link', componentId, entityId: data.id } });
      return;
    }

    setSelection({
      entity: { type: 'link', componentId, entityId: data.id },
      subType: 'collision',
      objectIndex: nextObjectIndex,
    });
  };

  return (
    <div className={isTabbed ? 'pt-1' : 'border-t border-border-black pt-4'}>
      {!isTabbed && (
        <div className="mb-2.5">
          <h3 className={`${PROPERTY_EDITOR_SECTION_TITLE_CLASS} capitalize`}>
            {category === 'visual' ? t.visualGeometry : t.collisionGeometry}
          </h3>
        </div>
      )}

      <div ref={geometryHeaderRowRef} className="mb-1 flex min-w-0 items-center gap-1.5">
        <GeometryEditorHeader
          category={category}
          currentGeometryType={currentGeometryType}
          geometryNameValue={geometryNameValue}
          geometryTypeOptions={geometryTypeOptions}
          isCompactGeometryActions={isCompactGeometryActions}
          linkName={data.name ?? ''}
          onAutoAlign={handleAutoAlign}
          onGeometryNameChange={(nextName) => update({ name: nextName })}
          onLinkNameChange={onLinkNameChange}
          onTypeChange={handleTypeChange}
          showAutoAlign={category === 'collision' && geomData.type === GeometryType.CYLINDER}
          t={t}
        />
      </div>

      {geomData.type === GeometryType.MESH && (
        <GeometryMeshLibraryPanel
          assets={assets}
          colladaRootNormalizationHints={colladaRootNormalizationHints}
          fileInputRef={fileInputRef}
          geometry={geomData}
          meshFiles={meshFiles}
          onApplyPreview={handleApplyMesh}
          onCommitMesh={(filePath) => {
            update({ meshPath: filePath });
            setPreviewMeshPath(null);
          }}
          onFileChange={handleFileChange}
          onPreviewMesh={setPreviewMeshPath}
          previewMeshPath={previewMeshPath}
          t={t}
        />
      )}

      <GeometryDimensionsSection geometry={geomData} onUpdate={update} t={t} />

      {geomData.type !== GeometryType.NONE && (
        <InputGroup label={t.originRelativeLink}>
          <TransformFields
            lang={lang}
            positionValue={displayedOrigin?.xyz || { x: 0, y: 0, z: 0 }}
            rotationValue={displayedOrigin?.rpy || { r: 0, p: 0, y: 0 }}
            compact={false}
            rotationQuickStepDegrees={90}
            onPositionChange={(v) =>
              update({
                origin: {
                  ...(displayedOrigin || { rpy: { r: 0, p: 0, y: 0 } }),
                  xyz: v as { x: number; y: number; z: number },
                },
              })
            }
            onRotationChange={(rpy) =>
              update({
                origin: { ...(displayedOrigin || { xyz: { x: 0, y: 0, z: 0 } }), rpy },
              })
            }
          />
        </InputGroup>
      )}

      {category === 'visual' && geomData.type !== GeometryType.NONE && (
        <VisualMaterialEditor
          assets={assets}
          authoredMaterialDisplayLabel={authoredMaterialDisplayLabel}
          displayedTextureAssetUrl={displayedTextureAssetUrl}
          displayedTexturePath={displayedTexturePath}
          effectiveColorValue={effectiveColorValue}
          effectiveOpacityValue={effectiveOpacityValue}
          effectiveTexturePath={effectiveTexturePath}
          geometry={geomData}
          hasReadonlyAuthoredMaterialDisplay={hasReadonlyAuthoredMaterialDisplay}
          isTextureReadonly={isTextureReadonly}
          materialSourceLabel={materialSourceLabel}
          onApplyTexturePreview={handleApplyTexture}
          onApplyVisualTexture={applyVisualTexture}
          onAuthoredMaterialColorChange={handleAuthoredMaterialColorChange}
          onAuthoredMaterialOpacityChange={handleAuthoredMaterialOpacityChange}
          onDeleteTextureAsset={handleDeleteTextureAsset}
          onPreviewTexturePathChange={setPreviewTexturePath}
          onSingleMaterialColorChange={handleSingleMaterialColorChange}
          onSingleMaterialOpacityChange={handleSingleMaterialOpacityChange}
          onTextureFileChange={handleTextureFileChange}
          previewTexturePath={previewTexturePath}
          t={t}
          textureFileInputRef={textureFileInputRef}
          textureFiles={textureFiles}
        />
      )}

      {category === 'collision' &&
        showCollisionDeleteAction &&
        geomData.type !== GeometryType.NONE && (
          <div className="mt-4 border-t border-border-black pt-3">
            <button
              type="button"
              onClick={handleDeleteCollision}
              className="inline-flex h-7 w-full items-center justify-center gap-1 rounded-md border border-red-200 bg-red-50 px-2 text-[10px] font-medium text-red-600 transition-colors hover:bg-red-100 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300 dark:hover:bg-red-900/30"
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span>{t.deleteCollisionGeometry}</span>
            </button>
          </div>
        )}
    </div>
  );
};

import type { RefObject } from 'react';
import { Check, Eye, File, Upload } from 'lucide-react';
import type { ColladaRootNormalizationHints } from '@/core/loaders/colladaRootNormalization';
import { shouldNormalizeColladaGeometry } from '@/core/loaders/colladaRootNormalization';
import type { UrdfVisual } from '@/types';
import {
  PROPERTY_EDITOR_HELPER_TEXT_CLASS,
  PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS,
  PROPERTY_EDITOR_PRIMARY_BUTTON_CLASS,
  PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS,
} from './FormControls';
import type { GeometryEditorTranslations } from './GeometryEditor.types';
import { MeshPreview } from './MeshPreview';
import { describeAssetPath } from './geometryEditorUtils';

interface GeometryMeshLibraryPanelProps {
  assets: Record<string, string>;
  colladaRootNormalizationHints: ColladaRootNormalizationHints | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  geometry: UrdfVisual;
  meshFiles: string[];
  onApplyPreview: () => void;
  onCommitMesh: (filePath: string) => void;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onPreviewMesh: (filePath: string | null) => void;
  previewMeshPath: string | null;
  t: GeometryEditorTranslations;
}

export const GeometryMeshLibraryPanel = ({
  assets,
  colladaRootNormalizationHints,
  fileInputRef,
  geometry,
  meshFiles,
  onApplyPreview,
  onCommitMesh,
  onFileChange,
  onPreviewMesh,
  previewMeshPath,
  t,
}: GeometryMeshLibraryPanelProps) => (
  <div className="mb-2 overflow-hidden rounded-lg border border-border-black bg-panel-bg/70">
    <div className="flex items-center justify-between gap-2 border-b border-border-black/60 bg-element-bg/70 px-2 py-1.5">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className={PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS}>{t.meshLibrary}</span>
        <span className="inline-flex min-w-4 items-center justify-center rounded-full border border-border-black bg-panel-bg px-1 py-0.5 text-[8px] font-semibold leading-none text-text-tertiary">
          {meshFiles.length}
        </span>
      </div>
      <div className="flex items-center gap-1">
        <input
          type="file"
          ref={fileInputRef}
          className="hidden"
          accept=".stl,.STL,.msh,.MSH,.obj,.OBJ,.dae,.DAE,.gltf,.GLTF,.glb,.GLB,.ply,.PLY,.vtk,.VTK"
          onChange={onFileChange}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="inline-flex h-6 items-center justify-center gap-1 rounded-md bg-system-blue-solid px-1.5 text-[10px] font-semibold text-white transition-colors hover:bg-system-blue-hover"
        >
          <Upload className="h-2.5 w-2.5" />
          {t.upload}
        </button>
      </div>
    </div>

    <div className="space-y-1 px-1.5 py-1.5">
      <div className="flex max-h-32 flex-col gap-0.5 overflow-y-auto custom-scrollbar pr-0.5">
        {meshFiles.length === 0 && (
          <div className="rounded-md border border-dashed border-border-black/70 bg-element-bg/70 px-2 py-3 text-center">
            <div className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} italic`}>{t.meshNotFound}</div>
          </div>
        )}
        {meshFiles.map((filePath) => {
          const isApplied = geometry.meshPath === filePath && !previewMeshPath;
          const isPreviewing = previewMeshPath === filePath;
          const { fileName, parentPath } = describeAssetPath(filePath);

          return (
            <button
              type="button"
              key={filePath}
              title={filePath}
              onClick={() => onPreviewMesh(filePath)}
              onDoubleClick={() => onCommitMesh(filePath)}
              className={`
                grid w-full cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-1.5 rounded-md border px-1.5 py-1 text-left transition-colors
                ${
                  isApplied
                    ? 'border-system-blue/35 bg-system-blue/10 text-system-blue dark:bg-system-blue/20'
                    : isPreviewing
                      ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                      : 'border-transparent bg-transparent text-text-secondary hover:border-border-black/50 hover:bg-element-hover'
                }
              `}
            >
              <File className="h-3 w-3 shrink-0" />
              <div className="min-w-0">
                <div
                  className={`truncate text-[10px] font-medium ${isApplied ? 'text-system-blue' : 'text-text-primary'}`}
                >
                  {fileName}
                </div>
                {parentPath && (
                  <div className="truncate text-[9px] leading-4 text-text-tertiary">
                    {parentPath}
                  </div>
                )}
              </div>
              {isApplied ? (
                <Check className="h-3 w-3 shrink-0" />
              ) : isPreviewing ? (
                <Eye className="h-3 w-3 shrink-0" />
              ) : null}
            </button>
          );
        })}
      </div>

      {previewMeshPath && (
        <div className="flex flex-col gap-1 rounded-md border border-border-black/60 bg-element-bg/70 p-1">
          <MeshPreview
            meshPath={previewMeshPath}
            assets={assets}
            normalizeColladaRoot={shouldNormalizeColladaGeometry(
              previewMeshPath,
              geometry.origin,
              colladaRootNormalizationHints,
            )}
            notFoundText={t.meshNotFound}
          />
          <div className="flex items-center gap-1">
            <button onClick={onApplyPreview} className={`${PROPERTY_EDITOR_PRIMARY_BUTTON_CLASS} flex-1`}>
              <Check className="h-2.5 w-2.5" />
              {t.applyMesh}
            </button>
            <button
              onClick={() => onPreviewMesh(null)}
              className={`${PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS} flex-1`}
            >
              {t.cancel}
            </button>
          </div>
        </div>
      )}

      {geometry.meshPath && !previewMeshPath && (
        <div className="rounded-md border border-system-blue/20 bg-system-blue/5 px-1.5 py-0.5">
          <div className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} truncate`}>
            {t.selected}: <span className="font-medium text-system-blue">{geometry.meshPath}</span>
          </div>
        </div>
      )}

      {!previewMeshPath && meshFiles.length > 0 && (
        <div className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} px-0.5`}>{t.meshHint}</div>
      )}
    </div>
  </div>
);

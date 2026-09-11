import { useCallback, useRef, useState, type ChangeEvent, type RefObject } from 'react';
import { Check, Eye, Trash2, Upload } from 'lucide-react';
import type { UrdfVisual } from '@/types';
import {
  getColorPickerHexValue,
  mergeColorOpacityValue,
  mergeColorPickerHexValue,
} from '../utils/colorInput';
import { getAuthoredMaterialOpacity } from '../utils/geometryMaterial';
import {
  InlineInputGroup,
  NumberInput,
  PROPERTY_EDITOR_HELPER_TEXT_CLASS,
  PROPERTY_EDITOR_INLINE_AXIS_LABEL_CLASS,
  PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS,
  PROPERTY_EDITOR_INPUT_CLASS,
  PROPERTY_EDITOR_PRIMARY_BUTTON_CLASS,
  PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS,
  PROPERTY_EDITOR_SECTION_TITLE_CLASS,
  ReadonlyValueField,
} from './FormControls';
import { DeferredColorPickerInput } from './DeferredColorPickerInput';
import type { GeometryEditorTranslations } from './GeometryEditor.types';
import { describeAssetPath } from './geometryEditorUtils';
import {
  MATERIAL_OPACITY_DECIMALS,
  MATERIAL_OPACITY_STEP,
} from './geometryEditorConstants';

const MATERIAL_PRESET_COLORS = [
  '#ff6c0a',
  '#007aff',
  '#34c759',
  '#ffcc00',
  '#af52de',
  '#ffffff',
  '#000000',
];
const MATERIAL_TONE_STEP = 0.07;
const MAX_RECENT_MATERIAL_COLORS = 6;

function normalizeHexColor(value?: string | null): string | null {
  const hex = getColorPickerHexValue(value || '', '').toLowerCase();
  return /^#[0-9a-f]{6}$/u.test(hex) ? hex : null;
}

function shiftHexChannel(channel: number, amount: number): number {
  if (amount >= 0) {
    return Math.round(channel + (255 - channel) * amount);
  }

  return Math.round(channel * (1 + amount));
}

function shiftHexColor(value: string, amount: number): string {
  const hex = normalizeHexColor(value) || '#ffffff';
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  return `#${channels
    .map((channel) => shiftHexChannel(channel, amount).toString(16).padStart(2, '0'))
    .join('')}`;
}

interface VisualMaterialEditorProps {
  assets: Record<string, string>;
  authoredMaterialDisplayLabel: string | null;
  displayedTextureAssetUrl: string | null;
  displayedTexturePath: string;
  effectiveColorValue: string;
  effectiveOpacityValue: number;
  effectiveTexturePath: string;
  geometry: UrdfVisual;
  hasReadonlyAuthoredMaterialDisplay: boolean;
  isTextureReadonly: boolean;
  materialSourceLabel: string | null;
  onApplyTexturePreview: () => void;
  onApplyVisualTexture: (texturePath: string | undefined) => void;
  onAuthoredMaterialColorChange: (index: number, newColor: string) => void;
  onAuthoredMaterialOpacityChange: (index: number, opacity: number) => void;
  onDeleteTextureAsset: (filePath: string) => void;
  onPreviewTexturePathChange: (filePath: string | null) => void;
  onSingleMaterialColorChange: (newColor: string) => void;
  onSingleMaterialOpacityChange: (opacity: number) => void;
  onTextureFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  previewTexturePath: string | null;
  t: GeometryEditorTranslations;
  textureFileInputRef: RefObject<HTMLInputElement | null>;
  textureFiles: string[];
}

export const VisualMaterialEditor = ({
  assets,
  authoredMaterialDisplayLabel,
  displayedTextureAssetUrl,
  displayedTexturePath,
  effectiveColorValue,
  effectiveOpacityValue,
  effectiveTexturePath,
  geometry,
  hasReadonlyAuthoredMaterialDisplay,
  isTextureReadonly,
  materialSourceLabel,
  onApplyTexturePreview,
  onApplyVisualTexture,
  onAuthoredMaterialColorChange,
  onAuthoredMaterialOpacityChange,
  onDeleteTextureAsset,
  onPreviewTexturePathChange,
  onSingleMaterialColorChange,
  onSingleMaterialOpacityChange,
  onTextureFileChange,
  previewTexturePath,
  t,
  textureFileInputRef,
  textureFiles,
}: VisualMaterialEditorProps) => {
  const initialAuthoredMaterialColorsRef = useRef<Record<string, string>>({});
  const [recentMaterialColors, setRecentMaterialColors] = useState<string[]>([]);

  const rememberRecentColor = useCallback((value?: string | null) => {
    const normalized = normalizeHexColor(value);
    if (!normalized) {
      return;
    }

    setRecentMaterialColors((current) =>
      [normalized, ...current.filter((color) => color !== normalized)].slice(
        0,
        MAX_RECENT_MATERIAL_COLORS,
      ),
    );
  }, []);

  const commitAuthoredMaterialColor = useCallback(
    (index: number, newColor: string, previousColor?: string | null) => {
      rememberRecentColor(previousColor);
      rememberRecentColor(newColor);
      onAuthoredMaterialColorChange(index, newColor);
    },
    [onAuthoredMaterialColorChange, rememberRecentColor],
  );

  return (
  <div className="mt-3 overflow-hidden rounded-lg border border-border-black bg-panel-bg/70">
    <div className="border-b border-border-black/60 bg-element-bg/70 px-2 py-1.5">
      <h4 className={PROPERTY_EDITOR_SECTION_TITLE_CLASS}>{t.material}</h4>
    </div>

    <div className="space-y-2 px-2 py-2">
      {materialSourceLabel ? (
        <InlineInputGroup label={t.materialSource} labelWidthClassName="w-16">
          <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
            {materialSourceLabel}
          </ReadonlyValueField>
        </InlineInputGroup>
      ) : null}

      <InlineInputGroup label={t.color} labelWidthClassName="whitespace-nowrap">
        {hasReadonlyAuthoredMaterialDisplay ? (
          <div className="space-y-1.5">
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {authoredMaterialDisplayLabel ?? ''}
            </ReadonlyValueField>
            <div className="flex flex-col gap-1">
              {(geometry.authoredMaterials || []).map((material, index) => {
                const materialLabel = material.name || `${t.material} ${index + 1}`;
                const materialKey = `${material.name || index}`;
                const currentColor = material.color || '';
                const normalizedCurrentColor = normalizeHexColor(currentColor);
                const initialColor =
                  initialAuthoredMaterialColorsRef.current[materialKey] ||
                  normalizeHexColor(currentColor) ||
                  '#ffffff';
                initialAuthoredMaterialColorsRef.current[materialKey] = initialColor;

                const applyColor = (nextColor: string) => {
                  commitAuthoredMaterialColor(
                    index,
                    mergeColorOpacityValue(nextColor, getAuthoredMaterialOpacity(material)),
                    currentColor,
                  );
                };

                return (
                  <div key={`${material.name || material.color || ''}-${index}`} className="space-y-1">
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={currentColor}
                        onChange={(event) =>
                          commitAuthoredMaterialColor(index, event.target.value, currentColor)
                        }
                        className={`${PROPERTY_EDITOR_INPUT_CLASS} flex-1 font-mono uppercase tracking-[0.04em] text-[10px]`}
                        spellCheck={false}
                      />
                      <span
                        aria-hidden="true"
                        className="h-5 w-5 shrink-0 rounded-full border border-border-black/70"
                        style={{ backgroundColor: currentColor || 'transparent' }}
                      />
                      <DeferredColorPickerInput
                        value={getColorPickerHexValue(currentColor)}
                        onCommit={(nextColor) =>
                          commitAuthoredMaterialColor(
                            index,
                            mergeColorOpacityValue(
                              mergeColorPickerHexValue(nextColor, currentColor),
                              getAuthoredMaterialOpacity(material),
                            ),
                            currentColor,
                          )
                        }
                        ariaLabel={`${t.color} ${materialLabel}`}
                        className="h-6 w-7 shrink-0 cursor-pointer rounded-md border border-border-strong bg-input-bg p-0.5 shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--color-border-black)_28%,transparent)]"
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        title={`${t.lighter} ${materialLabel} 7%`}
                        onClick={() => applyColor(shiftHexColor(currentColor, MATERIAL_TONE_STEP))}
                        className="h-5 rounded border border-border-black bg-element-bg px-1.5 text-[8px] font-medium text-text-secondary hover:bg-element-hover"
                      >
                        {t.lighter}
                      </button>
                      <button
                        type="button"
                        title={`${t.darker} ${materialLabel} 7%`}
                        onClick={() => applyColor(shiftHexColor(currentColor, -MATERIAL_TONE_STEP))}
                        className="h-5 rounded border border-border-black bg-element-bg px-1.5 text-[8px] font-medium text-text-secondary hover:bg-element-hover"
                      >
                        {t.darker}
                      </button>
                      <button
                        type="button"
                        title={`${t.reset} ${materialLabel}`}
                        onClick={() => applyColor(initialColor)}
                        className="h-5 rounded border border-border-black bg-element-bg px-1.5 text-[8px] font-medium text-text-secondary hover:bg-element-hover"
                      >
                        {t.reset}
                      </button>
                      {MATERIAL_PRESET_COLORS.map((presetColor) => (
                        <button
                          key={`${materialKey}-${presetColor}`}
                          type="button"
                          title={`${materialLabel} ${presetColor}`}
                          aria-label={`${materialLabel} ${presetColor}`}
                          onClick={() => applyColor(presetColor)}
                          className={`h-5 w-5 rounded-full border ${
                            normalizedCurrentColor === presetColor
                              ? 'border-system-blue ring-2 ring-system-blue/30'
                              : 'border-border-black'
                          }`}
                          style={{ backgroundColor: presetColor }}
                        />
                      ))}
                      {recentMaterialColors.map((recentColor) => (
                        <button
                          key={`${materialKey}-recent-${recentColor}`}
                          type="button"
                          title={`${t.recentColors} ${recentColor}`}
                          aria-label={`${t.recentColors} ${recentColor}`}
                          onClick={() => applyColor(recentColor)}
                          className="h-5 w-5 rounded-full border border-border-black"
                          style={{ backgroundColor: recentColor }}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={effectiveColorValue}
              onChange={(event) => onSingleMaterialColorChange(event.target.value)}
              className={`${PROPERTY_EDITOR_INPUT_CLASS} flex-1 font-mono uppercase tracking-[0.04em]`}
              spellCheck={false}
            />
            <span className={`${PROPERTY_EDITOR_INLINE_AXIS_LABEL_CLASS} w-auto whitespace-nowrap`}>
              HEX
            </span>
            <DeferredColorPickerInput
              value={getColorPickerHexValue(effectiveColorValue)}
              onCommit={(nextColor) => {
                const mergedColor = mergeColorPickerHexValue(nextColor, effectiveColorValue);
                onSingleMaterialColorChange(
                  effectiveOpacityValue < 0.999
                    ? mergeColorOpacityValue(mergedColor, effectiveOpacityValue)
                    : mergedColor,
                );
              }}
              ariaLabel={t.color}
              className="h-7 w-8 shrink-0 cursor-pointer rounded-md border border-border-strong bg-input-bg p-0.5 shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--color-border-black)_28%,transparent)]"
            />
          </div>
        )}
      </InlineInputGroup>

      <InlineInputGroup label={t.opacity} labelWidthClassName="whitespace-nowrap">
        {hasReadonlyAuthoredMaterialDisplay ? (
          <div className="flex flex-col gap-1">
            {(geometry.authoredMaterials || []).map((material, index) => (
              <div
                key={`${material.name || material.color || ''}-opacity-${index}`}
                className="grid min-w-0 grid-cols-[minmax(0,1fr)_4.75rem] items-center gap-1.5"
              >
                <span
                  className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} min-w-0 truncate`}
                  title={material.name || `${t.material} ${index + 1}`}
                >
                  {material.name || `${t.material} ${index + 1}`}
                </span>
                <NumberInput
                  value={getAuthoredMaterialOpacity(material)}
                  onChange={(value) => onAuthoredMaterialOpacityChange(index, value)}
                  min={0}
                  max={1}
                  step={MATERIAL_OPACITY_STEP}
                  precision={MATERIAL_OPACITY_DECIMALS}
                  compact
                  showStepper={false}
                  commitOnBlurOnly
                />
              </div>
            ))}
          </div>
        ) : (
          <NumberInput
            value={effectiveOpacityValue}
            onChange={onSingleMaterialOpacityChange}
            min={0}
            max={1}
            step={MATERIAL_OPACITY_STEP}
            precision={MATERIAL_OPACITY_DECIMALS}
            compact
            commitOnBlurOnly
          />
        )}
      </InlineInputGroup>

      <InlineInputGroup label={t.texture} labelWidthClassName="whitespace-nowrap">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-1.5">
            <ReadonlyValueField className="min-w-0 flex-1 bg-element-bg text-[10px] font-medium">
              <span className="block truncate">{displayedTexturePath || t.none}</span>
            </ReadonlyValueField>
            <input
              type="file"
              ref={textureFileInputRef}
              className="hidden"
              accept=".png,.PNG,.jpg,.JPG,.jpeg,.JPEG,.webp,.WEBP"
              onChange={onTextureFileChange}
            />
            {!isTextureReadonly && (
              <button
                type="button"
                onClick={() => textureFileInputRef.current?.click()}
                className={`${PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS} shrink-0`}
              >
                <Upload className="h-3 w-3" />
                <span>{t.uploadTexture}</span>
              </button>
            )}
            {!isTextureReadonly && effectiveTexturePath && (
              <button
                type="button"
                onClick={() => {
                  onPreviewTexturePathChange(null);
                  onApplyVisualTexture(undefined);
                }}
                className={`${PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS} shrink-0`}
              >
                <Trash2 className="h-3 w-3" />
                <span>{t.clearTexture}</span>
              </button>
            )}
          </div>
          {isTextureReadonly ? (
            <div className={PROPERTY_EDITOR_HELPER_TEXT_CLASS}>
              {t.textureReadonlyMultiMaterialHint}
            </div>
          ) : null}
        </div>
      </InlineInputGroup>

      {!isTextureReadonly && (
        <div className="mb-2 overflow-hidden rounded-lg border border-border-black bg-panel-bg/70">
          <div className="flex items-center justify-between gap-2 border-b border-border-black/60 bg-element-bg/70 px-2 py-1.5">
            <div className="flex min-w-0 items-center gap-1.5">
              <span className={PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS}>{t.textureLibrary}</span>
              <span className="inline-flex min-w-4 items-center justify-center rounded-full border border-border-black bg-panel-bg px-1 py-0.5 text-[8px] font-semibold leading-none text-text-tertiary">
                {textureFiles.length}
              </span>
            </div>
          </div>

          <div className="space-y-1 px-1.5 py-1.5">
            <div className="flex max-h-32 flex-col gap-0.5 overflow-y-auto custom-scrollbar pr-0.5">
              {textureFiles.length === 0 && (
                <div className="rounded-md border border-dashed border-border-black/70 bg-element-bg/70 px-2 py-3 text-center">
                  <div className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} italic`}>
                    {t.textureNotFound}
                  </div>
                </div>
              )}
              {textureFiles.map((filePath) => {
                const isApplied = effectiveTexturePath === filePath && !previewTexturePath;
                const isPreviewing = previewTexturePath === filePath;
                const { fileName, parentPath } = describeAssetPath(filePath);

                const rowStateClassName = isApplied
                  ? 'border-system-blue/35 bg-system-blue/10 text-system-blue dark:bg-system-blue/20'
                  : isPreviewing
                    ? 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                    : 'border-transparent bg-transparent text-text-secondary hover:border-border-black/50 hover:bg-element-hover';

                return (
                  <div
                    key={filePath}
                    className={`grid w-full grid-cols-[minmax(0,1fr)_auto] items-stretch gap-1 rounded-md border transition-colors ${rowStateClassName}`}
                  >
                    <button
                      type="button"
                      title={filePath}
                      onClick={() => onPreviewTexturePathChange(filePath)}
                      onDoubleClick={() => {
                        onApplyVisualTexture(filePath);
                        onPreviewTexturePathChange(null);
                      }}
                      className="grid min-w-0 cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-1.5 rounded-l-md px-1.5 py-1 text-left"
                    >
                      <span
                        aria-hidden="true"
                        className="h-3 w-3 shrink-0 rounded border border-border-black/70 bg-cover bg-center"
                        style={
                          assets[filePath]
                            ? { backgroundImage: `url("${assets[filePath]}")` }
                            : undefined
                        }
                      />
                      <span className="min-w-0">
                        <span
                          className={`block truncate text-[10px] font-medium ${
                            isApplied ? 'text-system-blue' : 'text-text-primary'
                          }`}
                        >
                          {fileName}
                        </span>
                        {parentPath && (
                          <span className="block truncate text-[9px] leading-4 text-text-tertiary">
                            {parentPath}
                          </span>
                        )}
                      </span>
                      {isApplied ? (
                        <Check className="h-3 w-3 shrink-0" />
                      ) : isPreviewing ? (
                        <Eye className="h-3 w-3 shrink-0" />
                      ) : null}
                    </button>
                    <button
                      type="button"
                      title={`${t.removeFromLibrary}: ${fileName}`}
                      aria-label={`${t.removeFromLibrary}: ${fileName}`}
                      onClick={() => onDeleteTextureAsset(filePath)}
                      className="flex w-7 shrink-0 items-center justify-center rounded-r-md border-l border-border-black/50 text-text-tertiary hover:bg-danger-soft hover:text-danger-hover"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {displayedTexturePath ? (
        <div className="flex flex-col gap-1 rounded-md border border-border-black/60 bg-element-bg/70 p-1">
          <div className="overflow-hidden rounded-md border border-border-black/60 bg-panel-bg/80">
            {displayedTextureAssetUrl ? (
              <img
                src={displayedTextureAssetUrl}
                alt={`${t.preview}: ${displayedTexturePath}`}
                className="block max-h-40 w-full object-contain"
              />
            ) : (
              <div className="flex min-h-28 items-center justify-center px-2 py-3 text-center">
                <div className={PROPERTY_EDITOR_HELPER_TEXT_CLASS}>{t.noPreviewImage}</div>
              </div>
            )}
          </div>
          {previewTexturePath ? (
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={onApplyTexturePreview}
                className={`${PROPERTY_EDITOR_PRIMARY_BUTTON_CLASS} flex-1`}
              >
                <Check className="h-2.5 w-2.5" />
                {t.apply}
              </button>
              <button
                type="button"
                onClick={() => onPreviewTexturePathChange(null)}
                className={`${PROPERTY_EDITOR_SECONDARY_BUTTON_CLASS} flex-1`}
              >
                {t.cancel}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  </div>
  );
};

import type { ChangeEvent } from 'react';
import { Wand } from 'lucide-react';
import { GeometryType } from '@/types';
import {
  PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS,
  PROPERTY_EDITOR_INPUT_CLASS,
  PropertyEditorSelect,
} from './FormControls';
import type {
  GeometryEditorCategory,
  GeometryEditorTranslations,
} from './GeometryEditor.types';
import { getGeometryTypeLabel } from './geometryEditorConstants';

interface GeometryEditorHeaderProps {
  category: GeometryEditorCategory;
  currentGeometryType: GeometryType;
  geometryNameValue: string;
  geometryTypeOptions: GeometryType[];
  isCompactGeometryActions: boolean;
  linkName: string;
  onAutoAlign: () => void;
  onGeometryNameChange: (name: string | undefined) => void;
  onLinkNameChange?: (name: string) => void;
  onTypeChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  showAutoAlign: boolean;
  t: GeometryEditorTranslations;
}

export const GeometryEditorHeader = ({
  category,
  currentGeometryType,
  geometryNameValue,
  geometryTypeOptions,
  isCompactGeometryActions,
  linkName,
  onAutoAlign,
  onGeometryNameChange,
  onLinkNameChange,
  onTypeChange,
  showAutoAlign,
  t,
}: GeometryEditorHeaderProps) => {
  const showLinkNameEditor = category === 'visual' && onLinkNameChange;

  return (
    <>
      {showLinkNameEditor ? (
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <span
            className={`${PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS} min-w-0 shrink whitespace-nowrap`}
          >
            {t.name}
          </span>
          <input
            type="text"
            value={linkName}
            onChange={(event) => onLinkNameChange(event.target.value)}
            className={`${PROPERTY_EDITOR_INPUT_CLASS} min-w-0 flex-1`}
            spellCheck={false}
          />
        </div>
      ) : (
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <span
            className={`${PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS} min-w-0 shrink whitespace-nowrap`}
          >
            {t.name}
          </span>
          <input
            type="text"
            value={geometryNameValue}
            onChange={(event) => onGeometryNameChange(event.target.value || undefined)}
            className={`${PROPERTY_EDITOR_INPUT_CLASS} min-w-0 flex-1`}
            spellCheck={false}
          />
        </div>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-1.5">
        <span
          className={`${PROPERTY_EDITOR_INLINE_FIELD_LABEL_CLASS} min-w-0 shrink whitespace-nowrap`}
        >
          {t.type}
        </span>
        <div
          className="min-w-0 flex-1"
          style={{
            height: 22,
            display: 'flex',
            alignItems: 'center',
            overflow: 'hidden',
            lineHeight: 0,
          }}
        >
          <PropertyEditorSelect
            value={currentGeometryType}
            aria-label={t.type}
            options={geometryTypeOptions.map((typeOption) => ({
              value: typeOption,
              label: getGeometryTypeLabel(typeOption, t),
            }))}
            onChange={onTypeChange}
            className="min-w-0 w-full"
          />
        </div>
      </div>
      {showAutoAlign && !isCompactGeometryActions ? (
        <button
          onClick={onAutoAlign}
          className="inline-flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-md border border-border-strong bg-element-bg text-text-tertiary transition-colors hover:bg-element-hover hover:text-text-primary"
          title={t.autoAlign}
        >
          <Wand className="h-3.5 w-3.5" />
        </button>
      ) : null}
    </>
  );
};

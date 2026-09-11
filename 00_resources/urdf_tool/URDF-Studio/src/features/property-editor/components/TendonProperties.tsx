import React from 'react';
import type {
  RobotMjcfInspectionTendonSummary,
  RobotMjcfTendonVisualizationUpdate,
} from '@/types';
import { formatNumberWithMaxDecimals } from '@/core/utils/numberPrecision';
import type { Language } from '@/store/uiStore';
import { translations } from '@/shared/i18n';
import {
  PROPERTY_EDITOR_HELPER_TEXT_CLASS,
  PROPERTY_EDITOR_INPUT_CLASS,
  PROPERTY_EDITOR_SUBLABEL_CLASS,
  NumberInput,
  ReadonlyValueField,
  StaticSection,
} from './FormControls';

interface TendonPropertiesProps {
  data: RobotMjcfInspectionTendonSummary;
  lang: Language;
  onUpdate?: (patch: RobotMjcfTendonVisualizationUpdate) => void;
}

interface TendonLabels {
  overview: string;
  attachments: string;
  actuators: string;
  name: string;
  type: string;
  className: string;
  group: string;
  limited: string;
  range: string;
  width: string;
  stiffness: string;
  springlength: string;
  rgba: string;
  target: string;
  extra: string;
  yes: string;
  no: string;
  none: string;
  attachmentType: Record<RobotMjcfInspectionTendonSummary['attachments'][number]['type'], string>;
}

const DEFAULT_TENDON_WIDTH = 0.003;
const DEFAULT_TENDON_RGBA: [number, number, number, number] = [1, 0, 0, 1];
const TENDON_COLOR_STEP = 0.01;
const TENDON_WIDTH_STEP = 0.001;
const TENDON_WIDTH_MIN = 0.0001;

function formatNumber(value: number | undefined): string {
  return typeof value === 'number' ? formatNumberWithMaxDecimals(value) : '-';
}

function formatOptionalText(value: string | undefined): string {
  const normalized = value?.trim();
  return normalized ? normalized : '-';
}

function formatRange(value: [number, number] | undefined): string {
  if (!value) {
    return '-';
  }

  return `${formatNumberWithMaxDecimals(value[0])} to ${formatNumberWithMaxDecimals(value[1])}`;
}

function clampUnitInterval(value: number): number {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.min(1, Math.max(0, value));
}

function normalizeRgba(value: [number, number, number, number] | undefined): [
  number,
  number,
  number,
  number,
] {
  const fallback = DEFAULT_TENDON_RGBA;
  return [
    clampUnitInterval(value?.[0] ?? fallback[0]),
    clampUnitInterval(value?.[1] ?? fallback[1]),
    clampUnitInterval(value?.[2] ?? fallback[2]),
    clampUnitInterval(value?.[3] ?? fallback[3]),
  ];
}

function channelToHex(value: number): string {
  return Math.round(clampUnitInterval(value) * 255)
    .toString(16)
    .padStart(2, '0');
}

function rgbaToHex(value: [number, number, number, number]): string {
  return `#${channelToHex(value[0])}${channelToHex(value[1])}${channelToHex(value[2])}`;
}

function mergeHexColorIntoRgba(
  hex: string,
  currentRgba: [number, number, number, number],
): [number, number, number, number] | null {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) {
    return null;
  }

  const raw = match[1];
  return [
    Number.parseInt(raw.slice(0, 2), 16) / 255,
    Number.parseInt(raw.slice(2, 4), 16) / 255,
    Number.parseInt(raw.slice(4, 6), 16) / 255,
    currentRgba[3],
  ];
}

interface DeferredColorPickerInputProps {
  ariaLabel: string;
  onCommit: (value: string) => void;
  value: string;
}

function DeferredColorPickerInput({
  ariaLabel,
  onCommit,
  value,
}: DeferredColorPickerInputProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [draftValue, setDraftValue] = React.useState(value);
  const draftValueRef = React.useRef(value);
  const committedValueRef = React.useRef(value);
  const onCommitRef = React.useRef(onCommit);

  React.useEffect(() => {
    onCommitRef.current = onCommit;
  }, [onCommit]);

  React.useEffect(() => {
    draftValueRef.current = value;
    committedValueRef.current = value;
    setDraftValue(value);
  }, [value]);

  const setDraft = React.useCallback((nextValue: string) => {
    draftValueRef.current = nextValue;
    setDraftValue((currentValue) => (currentValue === nextValue ? currentValue : nextValue));
  }, []);

  const commitDraft = React.useCallback(() => {
    const nextValue = draftValueRef.current;
    if (nextValue === committedValueRef.current) {
      return;
    }

    committedValueRef.current = nextValue;
    onCommitRef.current(nextValue);
  }, []);

  React.useEffect(() => {
    const input = inputRef.current;
    if (!input) {
      return;
    }

    const handleNativeChange = () => {
      setDraft(input.value);
      commitDraft();
    };

    input.addEventListener('change', handleNativeChange);
    return () => {
      input.removeEventListener('change', handleNativeChange);
    };
  }, [commitDraft, setDraft]);

  return (
    <input
      ref={inputRef}
      type="color"
      value={draftValue}
      onInput={(event) => setDraft(event.currentTarget.value)}
      onChange={(event) => setDraft(event.currentTarget.value)}
      onPointerUp={commitDraft}
      onMouseUp={commitDraft}
      onBlur={commitDraft}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          commitDraft();
        }
      }}
      aria-label={ariaLabel}
      className="h-6 w-8 shrink-0 cursor-pointer rounded-md border border-border-strong bg-input-bg p-0.5 shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--color-border-black)_28%,transparent)]"
    />
  );
}

export const TendonProperties: React.FC<TendonPropertiesProps> = ({ data, lang, onUpdate }) => {
  const t = translations[lang];
  const labels: TendonLabels = {
    overview: t.tendonOverview,
    attachments: t.tendonAttachments,
    actuators: t.tendonActuators,
    name: t.name,
    type: t.type,
    className: t.tendonClass,
    group: t.tendonGroup,
    limited: t.tendonLimited,
    range: t.tendonRange,
    width: t.tendonWidth,
    stiffness: t.tendonStiffness,
    springlength: t.tendonSpringLength,
    rgba: t.tendonRgba,
    target: t.tendonTarget,
    extra: t.tendonExtra,
    yes: t.yes,
    no: t.no,
    none: t.none,
    attachmentType: {
      site: 'site',
      geom: 'geom',
      joint: 'joint',
      pulley: 'pulley',
    },
  };
  const limitedValue =
    typeof data.limited === 'boolean' ? (data.limited ? labels.yes : labels.no) : '-';
  const editable = typeof onUpdate === 'function';
  const rgba = normalizeRgba(data.rgba);
  const colorHex = rgbaToHex(rgba);
  const updateTendon = React.useCallback(
    (updates: RobotMjcfTendonVisualizationUpdate) => {
      onUpdate?.(updates);
    },
    [onUpdate],
  );
  const updateRgbaChannel = React.useCallback(
    (index: 0 | 1 | 2 | 3, value: number) => {
      const nextRgba: [number, number, number, number] = [...rgba];
      nextRgba[index] = clampUnitInterval(value);
      updateTendon({ rgba: nextRgba });
    },
    [rgba, updateTendon],
  );
  const updateRgbaFromHex = React.useCallback(
    (value: string) => {
      const nextRgba = mergeHexColorIntoRgba(value, rgba);
      if (!nextRgba) {
        return;
      }

      updateTendon({ rgba: nextRgba });
    },
    [rgba, updateTendon],
  );

  return (
    <div className="space-y-2.5">
      <StaticSection title={labels.overview} className="mb-2.5">
        <div className="grid grid-cols-2 gap-1.5">
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.name}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {data.name}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.type}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium capitalize">
              {data.type}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.className}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {formatOptionalText(data.className)}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.group}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {typeof data.group === 'number' ? String(data.group) : '-'}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.limited}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {limitedValue}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.range}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {formatRange(data.range)}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.width}</div>
            {editable ? (
              <NumberInput
                value={data.width ?? DEFAULT_TENDON_WIDTH}
                onChange={(width) =>
                  updateTendon({ width: Math.max(TENDON_WIDTH_MIN, width) })
                }
                step={TENDON_WIDTH_STEP}
                min={TENDON_WIDTH_MIN}
                precision={5}
                compact
              />
            ) : (
              <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
                {formatNumber(data.width)}
              </ReadonlyValueField>
            )}
          </div>
          <div className="space-y-0.5">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.stiffness}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {formatNumber(data.stiffness)}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5 col-span-2">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.springlength}</div>
            <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
              {formatNumber(data.springlength)}
            </ReadonlyValueField>
          </div>
          <div className="space-y-0.5 col-span-2">
            <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.rgba}</div>
            {editable ? (
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-1.5">
                <div className="grid min-w-0 grid-cols-4 gap-1">
                  {(['R', 'G', 'B', 'A'] as const).map((channelLabel, index) => (
                    <NumberInput
                      key={channelLabel}
                      label={channelLabel}
                      value={rgba[index]}
                      onChange={(value) => updateRgbaChannel(index as 0 | 1 | 2 | 3, value)}
                      step={TENDON_COLOR_STEP}
                      min={0}
                      max={1}
                      precision={3}
                      compact
                      showStepper={false}
                    />
                  ))}
                </div>
                <DeferredColorPickerInput
                  ariaLabel={labels.rgba}
                  value={colorHex}
                  onCommit={updateRgbaFromHex}
                />
                <input
                  type="text"
                  value={colorHex}
                  onChange={(event) => updateRgbaFromHex(event.target.value)}
                  className={`${PROPERTY_EDITOR_INPUT_CLASS} col-span-2 font-mono uppercase`}
                  spellCheck={false}
                  aria-label={labels.rgba}
                />
              </div>
            ) : (
              <ReadonlyValueField className="bg-element-bg text-[10px] font-medium">
                {data.rgba?.length
                  ? data.rgba.map((entry) => formatNumberWithMaxDecimals(entry)).join(', ')
                  : '-'}
              </ReadonlyValueField>
            )}
          </div>
        </div>
      </StaticSection>

      <StaticSection title={labels.attachments} className="mb-2.5">
        {data.attachments.length > 0 ? (
          <div className="space-y-1.5">
            {data.attachments.map((attachment, index) => {
              const target = attachment.ref ?? attachment.sidesite ?? labels.none;
              const extras = [
                typeof attachment.coef === 'number'
                  ? `coef=${formatNumberWithMaxDecimals(attachment.coef)}`
                  : null,
                typeof attachment.divisor === 'number'
                  ? `divisor=${formatNumberWithMaxDecimals(attachment.divisor)}`
                  : null,
                attachment.sidesite ? `sidesite=${attachment.sidesite}` : null,
              ].filter(Boolean);

              return (
                <div
                  key={`${attachment.type}:${attachment.ref ?? attachment.sidesite ?? index}`}
                  className="rounded-md border border-border-black bg-element-bg/70 p-1.5"
                >
                  <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-1.5">
                    <div className="space-y-0.5">
                      <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.type}</div>
                      <ReadonlyValueField className="bg-element-bg text-[10px] font-medium capitalize">
                        {labels.attachmentType[attachment.type]}
                      </ReadonlyValueField>
                    </div>
                    <div className="space-y-0.5">
                      <div className={PROPERTY_EDITOR_SUBLABEL_CLASS}>{labels.target}</div>
                      <ReadonlyValueField className="min-w-0 bg-element-bg text-[10px] font-medium">
                        <span className="truncate">{target}</span>
                      </ReadonlyValueField>
                    </div>
                  </div>
                  {extras.length > 0 ? (
                    <div className={`${PROPERTY_EDITOR_HELPER_TEXT_CLASS} mt-1`}>
                      {labels.extra}: {extras.join(', ')}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className={PROPERTY_EDITOR_HELPER_TEXT_CLASS}>{labels.none}</div>
        )}
      </StaticSection>

      <StaticSection title={labels.actuators}>
        {data.actuatorNames.length > 0 ? (
          <div className="space-y-1">
            {data.actuatorNames.map((actuatorName) => (
              <ReadonlyValueField
                key={actuatorName}
                className="bg-element-bg text-[10px] font-medium"
              >
                {actuatorName}
              </ReadonlyValueField>
            ))}
          </div>
        ) : (
          <div className={PROPERTY_EDITOR_HELPER_TEXT_CLASS}>{labels.none}</div>
        )}
      </StaticSection>
    </div>
  );
};

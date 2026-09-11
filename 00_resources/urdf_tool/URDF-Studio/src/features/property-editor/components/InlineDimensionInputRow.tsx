import {
  NumberInput,
  PROPERTY_EDITOR_INLINE_AXIS_LABEL_CLASS,
} from './FormControls';
import type { DimensionInputField } from './GeometryEditor.types';
import {
  GEOMETRY_DIMENSION_STEP,
  MAX_GEOMETRY_DIMENSION_DECIMALS,
} from '@/core/utils/numberPrecision';

interface InlineDimensionInputRowProps {
  fields: DimensionInputField[];
  columns?: 1 | 2 | 3;
  labelClassName?: string;
  labelWidthClassName?: string;
  showStepper?: boolean;
}

export const InlineDimensionInputRow = ({
  fields,
  columns = 3,
  labelClassName = PROPERTY_EDITOR_INLINE_AXIS_LABEL_CLASS,
  labelWidthClassName = 'w-2 text-center',
  showStepper = true,
}: InlineDimensionInputRowProps) => (
  <div
    className={`min-w-0 ${
      columns === 1
        ? 'grid grid-cols-1 gap-1.5'
        : columns === 2
          ? 'grid grid-cols-2 gap-1.5'
          : 'grid grid-cols-3 gap-1.5'
    }`}
  >
    {fields.map((field) => (
      <div key={field.label} className="flex min-w-0 items-center gap-1.5">
        <span
          className={`${labelClassName} ${labelWidthClassName} min-w-0 shrink truncate`}
          title={field.label}
        >
          {field.label}
        </span>
        <div className="min-w-0 flex-1">
          <NumberInput
            value={field.value}
            onChange={field.onChange}
            min={field.min}
            max={field.max}
            compact
            showStepper={showStepper}
            step={GEOMETRY_DIMENSION_STEP}
            precision={MAX_GEOMETRY_DIMENSION_DECIMALS}
            commitOnBlurOnly
          />
        </div>
      </div>
    ))}
  </div>
);

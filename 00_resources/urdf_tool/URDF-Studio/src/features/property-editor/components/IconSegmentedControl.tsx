import React from 'react';
import {
  PROPERTY_EDITOR_ICON_SEGMENTED_BUTTON_CLASS,
  PROPERTY_EDITOR_ICON_SEGMENTED_GROUP_CLASS,
} from './formControlClasses';

export interface IconSegmentedOption<T extends string> {
  value: T;
  label: string;
  icon: React.ComponentType<{ className?: string; size?: number; strokeWidth?: number }>;
}

export const IconSegmentedControl = <T extends string>({
  value,
  onChange,
  options,
  ariaLabel,
}: {
  value: T;
  onChange: (value: T) => void;
  options: IconSegmentedOption<T>[];
  ariaLabel: string;
}) => (
  <div
    className={PROPERTY_EDITOR_ICON_SEGMENTED_GROUP_CLASS}
    style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    role="radiogroup"
    aria-label={ariaLabel}
  >
    {options.map((option) => {
      const Icon = option.icon;
      const isSelected = option.value === value;

      return (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={isSelected}
          aria-label={option.label}
          title={option.label}
          onClick={() => onChange(option.value)}
          className={`${PROPERTY_EDITOR_ICON_SEGMENTED_BUTTON_CLASS} ${
            isSelected
              ? 'bg-panel-bg text-system-blue shadow-sm ring-1 ring-border-black/60 dark:bg-segmented-active dark:text-white'
              : ''
          }`}
        >
          <Icon size={15} strokeWidth={isSelected ? 2.2 : 1.9} />
          <span className="sr-only">{option.label}</span>
        </button>
      );
    })}
  </div>
);

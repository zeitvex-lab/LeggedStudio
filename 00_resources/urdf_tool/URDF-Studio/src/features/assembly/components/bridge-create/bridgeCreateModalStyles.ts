import type { SelectOption } from '@/shared/components/ui';

export const BRIDGE_ROTATION_SHORTCUT_DEGREES = 90;
export const BRIDGE_HALF_ROTATION_DEGREES = 180;
export const BRIDGE_STEPPER_REPEAT_DELAY_MS = 300;
export const BRIDGE_STEPPER_REPEAT_INTERVAL_MS = 60;
export const BRIDGE_FIELD_LABEL_CLASS =
  'mb-0.5 block text-[10px] font-semibold uppercase tracking-[0.08em] leading-4 text-text-tertiary';
export const BRIDGE_FIELD_GROUP_CLASS = 'min-w-0';
export const BRIDGE_INSPECTOR_FIELD_ROW_CLASS = 'flex items-center gap-1.5';
export const BRIDGE_INLINE_FIELD_ROW_CLASS =
  'grid grid-cols-[auto_minmax(0,1fr)] items-center gap-1.5';
export const BRIDGE_INLINE_FIELD_LABEL_CLASS =
  'inline-flex h-[22px] min-w-0 shrink-0 items-center justify-end text-right text-[10px] font-semibold uppercase tracking-[0.06em] leading-4 text-text-tertiary';
export const BRIDGE_INLINE_FIELD_LABEL_WIDTH_CLASS = 'w-[88px]';
export const BRIDGE_SELECT_CLASS =
  '!h-[22px] !w-full min-w-0 rounded-md border border-border-strong bg-input-bg !px-1.5 !pr-6 !text-[10px] !leading-4 text-text-primary shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--color-border-black)_18%,transparent)] outline-none transition-colors focus:border-system-blue focus:ring-2 focus:ring-system-blue/25';
export const BRIDGE_PANEL_SELECT_CLASS = `${BRIDGE_SELECT_CLASS} !flex`;
export const BRIDGE_NUMBER_FIELD_SHELL_CLASS =
  'flex h-[22px] w-full items-stretch overflow-hidden rounded-md border border-border-strong bg-input-bg text-text-primary shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--color-border-black)_18%,transparent)] transition-colors focus-within:border-system-blue focus-within:ring-2 focus:ring-system-blue/25';
export const BRIDGE_NUMBER_INPUT_CLASS =
  'min-w-0 flex-1 bg-transparent px-1.5 text-[10px] leading-4 font-mono tracking-[-0.01em] text-text-primary tabular-nums outline-none';
export const BRIDGE_STEPPER_RAIL_CLASS =
  'flex w-4 shrink-0 flex-col border-l border-border-black/60 bg-element-bg/70';
export const BRIDGE_STEPPER_BUTTON_CLASS =
  'flex flex-1 min-h-0 items-center justify-center text-text-secondary transition-colors hover:bg-element-hover hover:text-text-primary focus:outline-none';
export const BRIDGE_QUICK_ROTATE_BUTTON_GROUP_CLASS =
  'grid h-5 shrink-0 grid-cols-2 overflow-hidden rounded-md border border-border-black/60 bg-element-bg/70';
export const BRIDGE_QUICK_ROTATE_BUTTON_CLASS =
  'inline-flex min-w-0 items-center justify-center px-0.5 text-[8px] font-semibold leading-none whitespace-nowrap text-text-secondary transition-colors hover:bg-element-hover hover:text-system-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/20';
export const BRIDGE_PICK_BUTTON_CLASS =
  'ml-auto shrink-0 rounded-md px-1.5 py-0.5 text-[8px] font-semibold transition-colors';
export const BRIDGE_SIDE_CARD_HEADER_ROW_CLASS =
  'grid grid-cols-[minmax(0,1fr)_auto] items-start gap-2';
export const BRIDGE_SIDE_CARD_ACTIONS_CLASS =
  'flex shrink-0 items-center gap-1.5 justify-self-end';
export const BRIDGE_RELATION_GRID_CLASS =
  'grid grid-cols-[minmax(0,1fr)_2.25rem_minmax(0,1fr)] items-stretch gap-1.5';
export const BRIDGE_COMPACT_RELATION_GRID_CLASS =
  'grid grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)_auto_auto_minmax(0,1fr)_minmax(0,1fr)] items-center gap-1.5';
export const BRIDGE_COMPACT_PICK_BUTTON_CLASS =
  'shrink-0 rounded-md px-1 py-0.5 text-[8px] font-semibold transition-colors whitespace-nowrap';
export const BRIDGE_TAB_CLASS =
  'bg-segmented-bg rounded-lg p-0.5 flex min-w-0';
export const BRIDGE_RELATION_CONNECTOR_LINE_CLASS =
  'w-px flex-1 bg-gradient-to-b from-border-black/0 via-border-black to-border-black/0';
export const BRIDGE_SECTION_CLASS =
  'rounded-lg border border-border-black/60 bg-transparent p-1.5';
export const BRIDGE_SECTION_TITLE_CLASS =
  'shrink-0 text-[10px] font-semibold uppercase tracking-[0.1em] leading-4 text-text-tertiary';
export const BRIDGE_EMPTY_SELECT_OPTION: SelectOption = { value: '', label: '--' };

export type BridgeAxisTone = 'x' | 'y' | 'z';

export const BRIDGE_AXIS_TONE_STYLES: Record<
  BridgeAxisTone,
  { badgeClassName: string; barClassName: string }
> = {
  x: {
    badgeClassName: 'border-danger-border bg-danger-soft text-danger',
    barClassName: 'bg-danger',
  },
  y: {
    badgeClassName: 'border-success-border bg-success-soft text-success',
    barClassName: 'bg-success',
  },
  z: {
    badgeClassName: 'border-system-blue/25 bg-system-blue/10 text-system-blue',
    barClassName: 'bg-system-blue',
  },
};

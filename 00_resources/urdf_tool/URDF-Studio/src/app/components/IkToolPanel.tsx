import React from 'react';

import { OptionsPanel } from '@/shared/components/Panel/OptionsPanel';
import { Select, type SelectOption } from '@/shared/components/ui/Select';
import type { TranslationKeys } from '@/shared/i18n/types';
import { useManagedWindowLayer } from '@/store';

import type { IkToolSelectionStatus } from '../utils/ikToolSelectionState';

const MIN_VISIBLE_PANEL_WIDTH = 56;
const MIN_VISIBLE_PANEL_HEADER_HEIGHT = 40;

function clampPanelPosition(
  nextPosition: { x: number; y: number },
  panelRect: DOMRect,
): { x: number; y: number } {
  const minX = Math.min(0, MIN_VISIBLE_PANEL_WIDTH - panelRect.width);
  const maxX = Math.max(0, window.innerWidth - MIN_VISIBLE_PANEL_WIDTH);
  const minY = 0;
  const maxY = Math.max(0, window.innerHeight - MIN_VISIBLE_PANEL_HEADER_HEIGHT);

  return {
    x: Math.max(minX, Math.min(nextPosition.x, maxX)),
    y: Math.max(minY, Math.min(nextPosition.y, maxY)),
  };
}

function useIkToolPanelDrag(show: boolean) {
  const panelRef = React.useRef<HTMLDivElement>(null);
  const dragOffsetRef = React.useRef<{ x: number; y: number } | null>(null);
  const bodyUserSelectRef = React.useRef('');
  const bodyCursorRef = React.useRef('');
  const [position, setPosition] = React.useState<{ x: number; y: number } | null>(null);

  const handleMouseMove = React.useCallback((event: MouseEvent) => {
    if (!panelRef.current || !dragOffsetRef.current) {
      return;
    }

    const panelRect = panelRef.current.getBoundingClientRect();
    const nextPosition = clampPanelPosition(
      {
        x: event.clientX - dragOffsetRef.current.x,
        y: event.clientY - dragOffsetRef.current.y,
      },
      panelRect,
    );
    setPosition(nextPosition);
  }, []);

  const handleMouseUp = React.useCallback(() => {
    dragOffsetRef.current = null;
    document.body.style.userSelect = bodyUserSelectRef.current;
    document.body.style.cursor = bodyCursorRef.current;
    document.removeEventListener('mousemove', handleMouseMove);
    document.removeEventListener('mouseup', handleMouseUp);
    window.removeEventListener('blur', handleMouseUp);
  }, [handleMouseMove]);

  const handleMouseDown = React.useCallback(
    (event: React.MouseEvent) => {
      if (event.button !== 0 || !panelRef.current) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();

      const panelRect = panelRef.current.getBoundingClientRect();
      dragOffsetRef.current = {
        x: event.clientX - panelRect.left,
        y: event.clientY - panelRect.top,
      };
      bodyUserSelectRef.current = document.body.style.userSelect;
      bodyCursorRef.current = document.body.style.cursor;
      document.body.style.userSelect = 'none';
      document.body.style.cursor = 'grabbing';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      window.addEventListener('blur', handleMouseUp);
    },
    [handleMouseMove, handleMouseUp],
  );

  React.useEffect(() => {
    if (show) {
      return;
    }

    setPosition(null);
    handleMouseUp();
  }, [handleMouseUp, show]);

  React.useEffect(
    () => () => {
      handleMouseUp();
    },
    [handleMouseUp],
  );

  return {
    panelRef,
    position,
    handleMouseDown,
  };
}

interface IkToolPanelProps {
  show: boolean;
  t: TranslationKeys;
  linkOptions: readonly SelectOption[];
  selectedLinkId: string | null;
  currentLinkLabel: string | null;
  selectedLinkLabel: string | null;
  selectionStatus: IkToolSelectionStatus;
  onSelectLink: (linkId: string) => void;
  onClose: () => void;
}

export const IkToolPanel: React.FC<IkToolPanelProps> = ({
  show,
  t,
  linkOptions,
  selectedLinkId,
  currentLinkLabel,
  selectedLinkLabel,
  selectionStatus,
  onSelectLink,
  onClose,
}) => {
  const [isCollapsed, setIsCollapsed] = React.useState(false);
  const ikToolLayer = useManagedWindowLayer('ikTool');
  const { panelRef, position, handleMouseDown } = useIkToolPanelDrag(show);
  const hasLinkOptions = linkOptions.length > 0;
  const selectOptions = React.useMemo(
    () => [
      {
        value: '',
        label: t.ikToolSelectPlaceholder,
      },
      ...linkOptions,
    ],
    [linkOptions, t.ikToolSelectPlaceholder],
  );
  const handleSelectLink = React.useCallback(
    (event: React.ChangeEvent<HTMLSelectElement>) => {
      const nextLinkId = event.currentTarget.value;
      if (!nextLinkId) {
        return;
      }

      onSelectLink(nextLinkId);
    },
    [onSelectLink],
  );

  const selectionLabel =
    selectedLinkLabel ??
    (selectionStatus !== 'idle' ? currentLinkLabel : null) ??
    t.ikToolNoSelection;

  const statusMessage =
    selectionStatus === 'root_not_draggable'
      ? t.ikToolRootLinkNotDraggable
      : selectionStatus === 'no_variable_chain'
        ? t.ikToolNoVariableChain
        : null;

  return (
    <OptionsPanel
      title={t.ikTool}
      show={show}
      onClose={onClose}
      showDragGrip
      position={position}
      defaultPosition={{ top: '64px', right: '16px' }}
      isCollapsed={isCollapsed}
      onToggleCollapse={() => setIsCollapsed((prev) => !prev)}
      onMouseDown={handleMouseDown}
      panelRef={panelRef}
      width="14rem"
      zIndex={ikToolLayer.zIndex}
      onActivate={ikToolLayer.onActivate}
      panelClassName="ik-tool-panel fixed z-50"
      expandText={t.expand}
      collapseText={t.collapse}
      closeText={t.close}
    >
      <div className="space-y-2 p-2">
        <p className="text-[11px] leading-relaxed text-text-secondary">{t.ikToolboxDesc}</p>
        <Select
          label={t.ikToolSelectLink}
          options={selectOptions}
          value={selectedLinkId ?? ''}
          onChange={handleSelectLink}
          disabled={!hasLinkOptions}
          containerClassName="space-y-1"
          labelClassName="text-[10px] font-medium uppercase tracking-[0.08em] text-text-muted"
          className="w-full text-[11px]"
          optionClassName="text-xs"
          optionButtonClassName="rounded-md px-2 py-1.5"
        />
        <div className="rounded-md border border-border-black/70 bg-panel-bg px-2 py-1.5">
          <div className="text-[10px] font-medium uppercase tracking-[0.08em] text-text-muted">
            {t.ikToolSelectedLink}
          </div>
          <div className="mt-1 break-all text-[11px] leading-relaxed text-text-primary">
            {selectionLabel}
          </div>
        </div>
        {statusMessage ? (
          <p className="rounded-md border border-system-blue/20 bg-system-blue/10 px-2 py-1.5 text-[11px] leading-relaxed text-system-blue">
            {statusMessage}
          </p>
        ) : null}
      </div>
    </OptionsPanel>
  );
};

export default IkToolPanel;

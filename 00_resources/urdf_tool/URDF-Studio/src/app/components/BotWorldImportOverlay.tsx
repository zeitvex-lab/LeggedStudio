import { translations, type Language } from '@/shared/i18n';
import type { ImportPhase } from '../hooks/useAssetImportFromUrl';
import type { ImportFromUrlProgress } from '../hooks/useAssetImportFromUrl';

interface BotWorldImportOverlayProps {
  phase: ImportPhase | null;
  progress: ImportFromUrlProgress | null;
  lang: Language;
}

const PHASE_TITLE_KEYS: Record<ImportPhase, keyof typeof translations.en> = {
  waiting: 'botWorldImportWaiting',
  fetching: 'botWorldImportFetching',
  downloading: 'botWorldImportDownloading',
  importing: 'botWorldImportImporting',
  complete: 'botWorldImportImporting',
};

export function BotWorldImportOverlay({ phase, progress, lang }: BotWorldImportOverlayProps) {
  if (!phase || phase === 'complete') return null;

  const t = translations[lang];
  const title = t[PHASE_TITLE_KEYS[phase]];

  const progressRatio = progress && progress.total > 0 ? progress.current / progress.total : null;

  const detail =
    progress && phase === 'downloading'
      ? progress.currentFileName
        ? `${progress.currentFileName} (${progress.current}/${progress.total})`
        : `${progress.current}/${progress.total}`
      : '';

  const statusLabel = progressRatio !== null ? `${Math.round(progressRatio * 100)}%` : null;

  const progressWidth = progressRatio !== null ? `${Math.round(progressRatio * 100)}%` : undefined;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/45 backdrop-blur-[4px]">
      <div
        role="status"
        aria-live="polite"
        className="min-w-[220px] max-w-[280px] rounded-2xl border border-border-black bg-panel-bg/95 px-3.5 py-3 shadow-xl backdrop-blur-sm"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-full bg-slider-accent motion-safe:animate-pulse"
              />
              <span className="truncate text-xs font-medium text-text-primary">{title}</span>
            </div>
          </div>
          {statusLabel ? (
            <div className="shrink-0 text-[11px] font-medium tabular-nums text-text-secondary">
              {statusLabel}
            </div>
          ) : null}
        </div>
        {detail ? (
          <div className="mt-2 truncate text-[11px] font-medium text-text-secondary">{detail}</div>
        ) : null}
        <div className="mt-3 h-1 overflow-hidden rounded-full bg-border-black/50">
          {progressRatio !== null ? (
            <div
              aria-hidden="true"
              className="h-full rounded-full bg-slider-accent transition-[width] duration-200 ease-out motion-reduce:transition-none"
              style={{ width: progressWidth }}
            />
          ) : (
            <div
              aria-hidden="true"
              className="h-full w-full rounded-full bg-[linear-gradient(90deg,rgba(0,136,255,0.12)_0%,rgba(0,136,255,0.4)_45%,rgba(0,136,255,0.12)_100%)] motion-safe:animate-pulse"
            />
          )}
        </div>
      </div>
    </div>
  );
}

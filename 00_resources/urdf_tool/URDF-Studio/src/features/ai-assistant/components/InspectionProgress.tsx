import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { TranslationKeys } from '@/shared/i18n';
import type { RobotInspectionStage } from '../services/aiService';
import type { InspectionRunContext } from '../utils/inspectionRunContext';

export interface InspectionProgressState {
  stage: RobotInspectionStage;
  selectedCount: number;
}

interface InspectionProgressProps {
  progress: InspectionProgressState;
  elapsedSeconds: number;
  runContext: InspectionRunContext;
  t: TranslationKeys;
}

interface StageDefinition {
  key: RobotInspectionStage;
  label: string;
  description: string;
}

const CAROUSEL_INTERVAL_MS = 4000;
const CAROUSEL_HEIGHT_BUFFER_PX = 12;
const CAROUSEL_SLIDE_KEYS = ['stage', 'profiles'] as const;

function formatElapsedTime(elapsedSeconds: number): string {
  if (elapsedSeconds < 60) {
    return `${elapsedSeconds}s`;
  }

  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;

  return `${minutes}m ${String(seconds).padStart(2, '0')}s`;
}

export function InspectionProgress({
  progress,
  elapsedSeconds,
  runContext,
  t,
}: InspectionProgressProps) {
  const stageDefinitions: StageDefinition[] = [
    {
      key: 'preparing-context',
      label: t.inspectionPreparingContext,
      description: t.inspectionPreparingContextDescription,
    },
    {
      key: 'requesting-model',
      label: t.inspectionRequestingModel,
      description: t.inspectionRequestingModelDescription,
    },
    {
      key: 'processing-response',
      label: t.inspectionProcessingResponse,
      description: t.inspectionProcessingResponseDescription,
    },
    {
      key: 'finalizing-report',
      label: t.inspectionFinalizingReport,
      description: t.inspectionFinalizingReportDescription,
    },
  ];
  const activeStageIndex = Math.max(
    stageDefinitions.findIndex((stage) => stage.key === progress.stage),
    0,
  );
  const activeStage = stageDefinitions[activeStageIndex] ?? stageDefinitions[0];
  const [activeCarouselSlideIndex, setActiveCarouselSlideIndex] = useState(0);
  const [carouselHeight, setCarouselHeight] = useState<number | null>(null);
  const carouselSlideContentRefs = useRef<Array<HTMLDivElement | null>>([]);

  const updateCarouselHeight = useCallback(() => {
    const activeSlideContent = carouselSlideContentRefs.current[activeCarouselSlideIndex];
    if (!activeSlideContent) {
      return;
    }

    const nextHeight = Math.ceil(activeSlideContent.scrollHeight) + CAROUSEL_HEIGHT_BUFFER_PX;
    if (nextHeight <= 0) {
      return;
    }

    setCarouselHeight((previousHeight) =>
      previousHeight === nextHeight ? previousHeight : nextHeight,
    );
  }, [activeCarouselSlideIndex]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setActiveCarouselSlideIndex(
        (previousIndex) => (previousIndex + 1) % CAROUSEL_SLIDE_KEYS.length,
      );
    }, CAROUSEL_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, []);

  useLayoutEffect(() => {
    updateCarouselHeight();
  });

  return (
    <div
      data-inspection-running-shell="true"
      className="mx-auto flex min-h-full w-full max-w-5xl flex-col justify-center py-2"
    >
      <div
        data-inspection-running-console="true"
        className="inspection-running-console relative overflow-hidden rounded-2xl border border-border-black bg-panel-bg p-5 shadow-sm"
      >
        <div
          aria-hidden="true"
          className="inspection-running-sweep absolute inset-y-0 left-0 w-1/2"
        />
        <div className="relative grid min-h-[360px] gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="flex items-center justify-center">
            <div
              data-inspection-running-scan-core="true"
              className="inspection-running-orbit relative flex h-40 w-40 items-center justify-center rounded-full border border-system-blue/20 bg-system-blue/5"
            >
              <span className="inspection-running-ring absolute inset-4 rounded-full border border-system-blue/25" />
              <span className="inspection-running-ring inspection-running-ring-delayed absolute inset-9 rounded-full border border-system-blue/20" />
              <span className="absolute h-px w-28 bg-system-blue/30" />
              <span className="absolute h-28 w-px bg-system-blue/20" />
              <span className="relative flex h-16 w-16 items-center justify-center rounded-2xl border border-system-blue/25 bg-panel-bg text-system-blue shadow-sm">
                <Loader2 className="h-7 w-7 animate-spin" />
              </span>
            </div>
          </div>

          <div className="flex min-w-0 flex-col justify-center">
            <div
              data-inspection-running-title-row="true"
              className="flex flex-wrap items-center gap-x-3 gap-y-1"
            >
              <h2 className="text-2xl font-semibold leading-tight text-text-primary">
                {activeStage.label}
              </h2>
              <span
                data-inspection-elapsed-badge="true"
                className="mt-0.5 rounded-lg border border-border-black bg-element-bg px-2 py-0.5 text-xs font-medium text-text-tertiary"
              >
                {t.inspectionElapsedTime} {formatElapsedTime(elapsedSeconds)}
              </span>
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
              {activeStage.description}
            </p>

            <div
              data-inspection-running-carousel="true"
              className="inspection-running-carousel relative mt-6 min-h-16 overflow-hidden rounded-xl border border-border-black bg-element-bg"
              style={carouselHeight ? { height: `${carouselHeight}px` } : undefined}
            >
              <div
                data-inspection-running-carousel-slide="stage"
                data-inspection-running-carousel-slide-active={
                  activeCarouselSlideIndex === 0 ? 'true' : undefined
                }
                className="inspection-running-carousel-slide"
              >
                <div
                  data-inspection-running-carousel-slide-content="stage"
                  ref={(node) => {
                    carouselSlideContentRefs.current[0] = node;
                  }}
                  className="p-3"
                >
                  <div className="text-xs font-medium text-text-tertiary">
                    {t.inspectionRunStage}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-text-primary">
                    {activeStage.label}
                  </div>
                  <div className="mt-1 text-xs leading-5 text-text-secondary">
                    {activeStage.description}
                  </div>
                </div>
              </div>
              <div
                data-inspection-running-carousel-slide="profiles"
                data-inspection-running-carousel-slide-active={
                  activeCarouselSlideIndex === 1 ? 'true' : undefined
                }
                className="inspection-running-carousel-slide"
              >
                <div
                  data-inspection-running-carousel-slide-content="profiles"
                  ref={(node) => {
                    carouselSlideContentRefs.current[1] = node;
                  }}
                  className="p-3"
                >
                  <div className="text-xs font-medium text-text-tertiary">
                    {t.inspectionSelectedCategories}
                  </div>
                  <div className="mt-1 text-sm font-semibold text-text-primary">
                    {t.inspectionSelectedChecks.replace(
                      '{count}',
                      String(runContext.selectedCount),
                    )}
                    {' · '}
                    {t.inspectionSelectedCategories}: {runContext.selectedProfileCount}
                  </div>
                  <div className="mt-2 flex max-w-full flex-wrap gap-2">
                    {runContext.profileSummary.map((profile) => (
                      <span
                        key={profile.id}
                        data-inspection-running-profile-chip="true"
                        className="whitespace-nowrap rounded-lg border border-border-black bg-panel-bg px-2 py-0.5 text-[11px] font-medium leading-5 text-text-secondary"
                      >
                        {profile.name} {profile.selectedCount}/{profile.totalCount}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {runContext.evidenceSummary && (
            <div className="lg:col-span-2">
              <div className="flex flex-wrap items-center gap-2 border-t border-border-black pt-3">
                <span className="text-xs font-medium text-text-tertiary">
                  {runContext.evidenceSummary.title}
                </span>
                {runContext.evidenceSummary.metrics.map((metric) => (
                  <span
                    key={`${metric.label}:${metric.value}`}
                    className="rounded-lg border border-border-black bg-element-bg px-2.5 py-1.5 text-xs font-medium text-text-secondary"
                  >
                    {metric.label}: {metric.value}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default InspectionProgress;

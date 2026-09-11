import { ChevronDown, ChevronRight, RotateCcw, Sparkles } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Language, TranslationKeys } from '@/shared/i18n'
import {
  getInspectionProfileLayerName,
  getInspectionProfileName,
} from '../config/inspectionProfiles'
import type { SelectedInspectionProfiles } from '../utils/inspectionProfileSelection'
import type { NormalInspectionPlan } from '../utils/inspectionNormalPlan'
import {
  buildInspectionLayerSummaries,
  buildInspectionProfileScopeSummaries,
  buildInspectionSelectionDeviation,
} from '../utils/inspectionAdvancedScopeViewModel'

interface InspectionRecommendationBannerProps {
  lang: Language
  t: TranslationKeys
  plan: NormalInspectionPlan
  selectedProfiles: SelectedInspectionProfiles
  recommendedProfiles: SelectedInspectionProfiles
  focusedProfileId: string
  totalItemCount: number
  onFocusProfile: (profileId: string) => void
  onRestoreRecommendation: () => void
}

const countSelectedItems = (selectedProfiles: SelectedInspectionProfiles) =>
  Object.values(selectedProfiles).reduce((sum, itemIds) => sum + itemIds.size, 0)

function formatRecommendationReason(reason: string, t: TranslationKeys) {
  if (reason.startsWith('source_format:')) {
    return `${t.inspectionRecommendationSourceFormat}: ${reason
      .slice('source_format:'.length)
      .toUpperCase()}`
  }
  if (reason.startsWith('target:')) {
    return `${t.inspectionRecommendationTarget}: ${reason.slice('target:'.length)}`
  }
  if (reason === 'workflow:assembly') return t.inspectionReasonAssembly
  if (reason === 'workflow:hardware_config') return t.inspectionReasonHardwareConfig
  if (reason === 'workflow:export_preflight') return t.inspectionReasonExportPreflight
  if (reason === 'workflow:collision_authoring') return t.inspectionReasonCollisionAuthoring
  if (reason === 'workflow:inertia_authoring') return t.inspectionReasonInertiaAuthoring
  if (reason.startsWith('purpose:')) {
    return `${t.inspectionPlanPurpose}: ${reason.slice('purpose:'.length)}`
  }
  return reason
}

export function InspectionRecommendationBanner({
  lang,
  t,
  plan,
  selectedProfiles,
  recommendedProfiles,
  focusedProfileId,
  totalItemCount,
  onFocusProfile,
  onRestoreRecommendation,
}: InspectionRecommendationBannerProps) {
  const [isReasonExpanded, setIsReasonExpanded] = useState(false)
  const selectedCount = countSelectedItems(selectedProfiles)
  const deviation = useMemo(
    () => buildInspectionSelectionDeviation(selectedProfiles, recommendedProfiles),
    [recommendedProfiles, selectedProfiles],
  )
  const reasons = plan.reasons.map((reason) => formatRecommendationReason(reason, t))
  const deviationSummary = t.inspectionRecommendationDeviationSummary.replace(
    '{count}',
    String(deviation.totalChangedItemCount),
  )
  const layerSummaries = useMemo(
    () => buildInspectionLayerSummaries(selectedProfiles, recommendedProfiles),
    [recommendedProfiles, selectedProfiles],
  )
  const profileSummaries = useMemo(
    () => buildInspectionProfileScopeSummaries(selectedProfiles, recommendedProfiles),
    [recommendedProfiles, selectedProfiles],
  )
  const visibleProfileSummariesByLayer = useMemo(() => {
    const byLayer = new Map<string, typeof profileSummaries>()

    profileSummaries
      .filter((summary) => summary.selectedItemCount > 0 || summary.recommendedItemCount > 0)
      .forEach((summary) => {
        const summaries = byLayer.get(summary.layer) ?? []
        summaries.push(summary)
        byLayer.set(summary.layer, summaries)
      })

    return byLayer
  }, [profileSummaries])

  return (
    <section
      data-inspection-recommendation-banner
      className="rounded-xl border border-system-blue/20 bg-system-blue/5 p-3 shadow-sm"
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-start gap-2">
            <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-system-blue/20 bg-panel-bg text-system-blue">
              <Sparkles className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-semibold text-text-primary">
                  {t.inspectionRecommendationArchitecture}
                </h2>
                <span className="rounded-md border border-system-blue/15 bg-panel-bg px-2 py-0.5 text-[10px] font-semibold text-system-blue">
                  {selectedCount}/{totalItemCount}
                </span>
                {deviation.totalChangedItemCount > 0 && (
                  <span
                    data-inspection-recommendation-custom-state="true"
                    className="rounded-md border border-warning-border bg-warning-soft px-2 py-0.5 text-[10px] font-semibold text-warning"
                  >
                    {deviationSummary}
                  </span>
                )}
              </div>
              <p className="mt-1 text-[12px] leading-5 text-text-secondary">
                {t.inspectionRecommendationArchitectureDescription}
              </p>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {reasons.length > 0 && (
            <button
              type="button"
              onClick={() => setIsReasonExpanded((current) => !current)}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border-black bg-panel-bg px-3 text-[11px] font-medium text-text-secondary transition-colors hover:bg-element-hover hover:text-system-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30"
            >
              {isReasonExpanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
              {isReasonExpanded
                ? t.inspectionHideRecommendationReasons
                : t.inspectionRecommendationReasons}
            </button>
          )}
          <button
            type="button"
            onClick={onRestoreRecommendation}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-system-blue/25 bg-panel-bg px-3 text-[11px] font-semibold text-system-blue transition-colors hover:bg-system-blue/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t.inspectionRestoreRecommendation}
          </button>
        </div>
      </div>

      <div
        data-inspection-recommendation-architecture="true"
        className="mt-3 grid gap-2 md:grid-cols-2"
      >
        {layerSummaries
          .filter(
            (layerSummary) =>
              layerSummary.selectedItemCount > 0 || layerSummary.recommendedItemCount > 0,
          )
          .map((layerSummary) => {
            const profiles = visibleProfileSummariesByLayer.get(layerSummary.layer) ?? []
            return (
              <div
                key={layerSummary.layer}
                data-inspection-recommendation-layer={layerSummary.layer}
                className="rounded-lg border border-border-black bg-panel-bg px-3 py-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 text-[11px] font-semibold text-text-primary">
                    {getInspectionProfileLayerName(layerSummary.layer, lang)}
                  </div>
                  <span className="shrink-0 rounded-md border border-border-black bg-element-bg px-1.5 py-0.5 text-[10px] font-semibold text-text-tertiary">
                    {profiles.filter((profile) => profile.selectedItemCount > 0).length}/
                    {profiles.length}
                  </span>
                </div>
                <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                  {profiles.map((profile) => {
                    const isFocused = profile.profileId === focusedProfileId
                    const isCustom =
                      profile.relation === 'partial' ||
                      profile.relation === 'user_added' ||
                      profile.relation === 'user_removed'
                    const isSelected = profile.selectedItemCount > 0
                    return (
                      <button
                        key={profile.profileId}
                        type="button"
                        data-inspection-recommendation-profile={profile.profileId}
                        data-inspection-recommendation-profile-custom={
                          isCustom ? 'true' : undefined
                        }
                        onClick={() => onFocusProfile(profile.profileId)}
                        className={`min-w-0 rounded-lg border px-2 py-1.5 text-left text-[10px] font-medium leading-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30 ${
                          isFocused
                            ? 'border-system-blue/40 bg-system-blue/10 text-system-blue shadow-sm'
                            : isSelected
                              ? 'border-border-black bg-element-bg text-text-secondary hover:border-system-blue/30 hover:text-system-blue'
                              : 'border-border-black bg-panel-bg text-text-tertiary hover:bg-element-hover'
                        }`}
                      >
                        <span className="block truncate">
                          {getInspectionProfileName(profile.profileId, lang)}
                        </span>
                        <span className="mt-0.5 block text-[9px] text-text-tertiary">
                          {profile.selectedItemCount}/{profile.totalItemCount}
                          {isCustom ? ` · ${deviationSummary}` : ''}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
      </div>

      {isReasonExpanded && reasons.length > 0 && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {reasons.map((reason) => (
            <div
              key={reason}
              className="rounded-lg border border-border-black bg-panel-bg px-3 py-2 text-[11px] font-medium text-text-secondary"
            >
              {reason}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default InspectionRecommendationBanner

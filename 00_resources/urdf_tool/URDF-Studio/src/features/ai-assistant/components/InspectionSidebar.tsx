import { Check, ChevronDown, ChevronRight, FileText, Layers, Minus, Package, Sparkles, Target } from 'lucide-react';
import { useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { Language, TranslationKeys } from '@/shared/i18n';
import {
  INSPECTION_PROFILE_DEFINITIONS,
  getInspectionProfileLayerName,
} from '../config/inspectionProfiles';
import {
  buildInspectionLayerSummaries,
  buildInspectionProfileScopeSummaries,
  buildInspectionSelectionDeviation,
} from '../utils/inspectionAdvancedScopeViewModel';
import type { SelectedInspectionProfiles } from '../utils/inspectionProfileSelection';

interface InspectionSidebarProps {
  lang: Language;
  t: TranslationKeys;
  isGeneratingAI: boolean;
  readOnly?: boolean;
  navigationOnly?: boolean;
  focusedProfileId: string;
  expandedProfiles: Set<string>;
  selectedProfiles: SelectedInspectionProfiles;
  recommendedProfiles?: SelectedInspectionProfiles;
  setExpandedProfiles: Dispatch<SetStateAction<Set<string>>>;
  setSelectedProfiles: Dispatch<SetStateAction<SelectedInspectionProfiles>>;
  onFocusProfile: (profileId: string) => void;
  onNavigateToProfile?: (profileId: string) => void;
  onNavigateToItem?: (profileId: string, itemId: string) => void;
  onNavigateToSetupItem?: (profileId: string, itemId: string) => void;
}

const getProfileIcon = (layer: string) => {
  if (layer === 'base') return Layers;
  if (layer === 'format') return FileText;
  if (layer === 'target') return Target;
  if (layer === 'workflow') return Package;
  return Sparkles;
};

export function InspectionSidebar({
  lang,
  t,
  isGeneratingAI,
  readOnly = false,
  navigationOnly = false,
  focusedProfileId,
  expandedProfiles,
  selectedProfiles,
  recommendedProfiles = selectedProfiles,
  setExpandedProfiles,
  setSelectedProfiles,
  onFocusProfile,
  onNavigateToProfile,
  onNavigateToItem,
  onNavigateToSetupItem,
}: InspectionSidebarProps) {
  const [expandedLayers, setExpandedLayers] = useState(
    () => new Set(['base', 'morph', 'format', 'target', 'workflow']),
  );
  const isNavigationOnly = navigationOnly && !readOnly;
  const isInteractionLocked = isGeneratingAI;
  const isRunningInspection = isGeneratingAI && readOnly;
  const totalItemCount = INSPECTION_PROFILE_DEFINITIONS.reduce(
    (sum, profile) => sum + profile.items.length,
    0,
  );
  let totalSelectedCount = 0;
  let selectedProfileCount = 0;

  INSPECTION_PROFILE_DEFINITIONS.forEach((profile) => {
    const count = selectedProfiles[profile.id]?.size ?? 0;
    totalSelectedCount += count;
    if (count > 0) {
      selectedProfileCount += 1;
    }
  });

  const visibleProfiles = readOnly
    ? INSPECTION_PROFILE_DEFINITIONS.filter((profile) => (selectedProfiles[profile.id]?.size ?? 0) > 0)
    : INSPECTION_PROFILE_DEFINITIONS;
  const visibleProfileIds = new Set(visibleProfiles.map((profile) => profile.id));
  const layerSummaries = buildInspectionLayerSummaries(selectedProfiles, recommendedProfiles)
    .map((summary) => ({
      ...summary,
      profileIds: summary.profileIds.filter((profileId) => visibleProfileIds.has(profileId)),
    }))
    .filter((summary) => summary.profileIds.length > 0);
  const profileSummaries = new Map(
    buildInspectionProfileScopeSummaries(selectedProfiles, recommendedProfiles).map((summary) => [
      summary.profileId,
      summary,
    ]),
  );
  const profileDeltaCounts = new Map<string, { added: number; removed: number }>();
  const selectionDeviation = buildInspectionSelectionDeviation(
    selectedProfiles,
    recommendedProfiles,
  );
  selectionDeviation.addedItems.forEach(({ profileId }) => {
    const current = profileDeltaCounts.get(profileId) ?? { added: 0, removed: 0 };
    current.added += 1;
    profileDeltaCounts.set(profileId, current);
  });
  selectionDeviation.removedItems.forEach(({ profileId }) => {
    const current = profileDeltaCounts.get(profileId) ?? { added: 0, removed: 0 };
    current.removed += 1;
    profileDeltaCounts.set(profileId, current);
  });

  const toggleProfileSelection = (profileId: string) => {
    setSelectedProfiles((prev) => {
      const next = { ...prev };
      const profile = INSPECTION_PROFILE_DEFINITIONS.find((entry) => entry.id === profileId);
      if (!profile) return prev;

      const allSelected = profile.items.every((item) => next[profileId]?.has(item.id));
      next[profileId] = allSelected ? new Set() : new Set(profile.items.map((item) => item.id));
      return next;
    });
  };

  const toggleItemSelection = (profileId: string, itemId: string) => {
    setSelectedProfiles((prev) => {
      const next = { ...prev };
      const itemSet = new Set(next[profileId] ?? []);
      if (itemSet.has(itemId)) {
        itemSet.delete(itemId);
      } else {
        itemSet.add(itemId);
      }
      next[profileId] = itemSet;
      return next;
    });
  };

  const toggleProfileExpand = (profileId: string) => {
    setExpandedProfiles((prev) => {
      const next = new Set(prev);
      if (next.has(profileId)) {
        next.delete(profileId);
      } else {
        next.add(profileId);
      }
      return next;
    });
  };

  const toggleLayerExpand = (layer: string) => {
    setExpandedLayers((prev) => {
      const next = new Set(prev);
      if (next.has(layer)) {
        next.delete(layer);
      } else {
        next.add(layer);
      }
      return next;
    });
  };

  return (
    <div
      data-inspection-sidebar
      className="flex min-h-0 w-72 shrink-0 flex-col overflow-hidden border-r border-border-black bg-panel-bg dark:bg-element-bg"
    >
      <div className="shrink-0 border-b border-border-black bg-element-bg p-3">
        <div className="min-w-0">
          <h3 className="px-1 text-[10px] font-medium tracking-wide text-text-tertiary">
            {isNavigationOnly ? t.inspectionArchitectureNavigation : t.inspectionItems}
          </h3>
          <p className="mt-1 px-1 text-[11px] leading-4 text-text-secondary">
            {isNavigationOnly
              ? t.inspectionArchitectureNavigationDescription
              : t.inspectionScopeDescription}
          </p>
        </div>

        <div
          className={`mt-3 rounded-xl border p-2.5 ${
            isRunningInspection
              ? 'border-system-blue/20 bg-system-blue/5'
              : 'border-border-black bg-panel-bg'
          }`}
        >
          <div className="flex items-center justify-between text-[10px] font-medium uppercase tracking-[0.08em] text-text-tertiary">
            <span>{isNavigationOnly ? t.inspectionSelectedCategories : t.runInspection}</span>
            <span>
              {selectedProfileCount}/{INSPECTION_PROFILE_DEFINITIONS.length}
            </span>
          </div>
          <div className="mt-1 text-xs font-semibold text-text-primary">
            {t.inspectionSelectedChecksSummary
              .replace('{selected}', String(totalSelectedCount))
              .replace('{total}', String(totalItemCount))}
          </div>
        </div>
      </div>

      <div
        className={`custom-scrollbar min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-2 space-y-2 ${
          isInteractionLocked ? 'opacity-70' : ''
        }`}
      >
        {layerSummaries.map((layerSummary) => {
          const layerName = getInspectionProfileLayerName(layerSummary.layer, lang);
          const isLayerExpanded = expandedLayers.has(layerSummary.layer);

          return (
            <section
              key={layerSummary.layer}
              data-inspection-sidebar-layer
              className="rounded-xl border border-border-black bg-panel-bg shadow-sm"
            >
              <button
                type="button"
                data-inspection-sidebar-layer-toggle={layerSummary.layer}
                aria-expanded={isLayerExpanded}
                disabled={isInteractionLocked}
                className="flex w-full items-center justify-between gap-2 border-b border-border-black/70 px-2.5 py-2 text-left transition-colors hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
                onClick={() => toggleLayerExpand(layerSummary.layer)}
              >
                <span className="flex min-w-0 items-center gap-2">
                  {isLayerExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-tertiary" />
                  )}
                  <span className="truncate text-[11px] font-semibold text-text-primary">
                    {layerName}
                  </span>
                </span>
                <span className="shrink-0 rounded-md border border-border-black bg-element-bg px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-text-secondary">
                  {layerSummary.selectedItemCount}/{layerSummary.totalItemCount}
                </span>
              </button>

              {isLayerExpanded && <div className="space-y-1 p-1.5">
                {layerSummary.profileIds.map((profileId) => {
                  const profile = INSPECTION_PROFILE_DEFINITIONS.find(
                    (entry) => entry.id === profileId,
                  );
                  if (!profile) return null;

                  const profileName = lang === 'zh' ? profile.nameZh : profile.name;
                  const selectedItemIds = selectedProfiles[profile.id] || new Set();
                  const selectedCount = selectedItemIds.size;
                  const allSelected = profile.items.every((item) => selectedItemIds.has(item.id));
                  const someSelected = profile.items.some((item) => selectedItemIds.has(item.id));
                  const isExpanded = expandedProfiles.has(profile.id);
                  const isFocused = focusedProfileId === profile.id;
                  const visibleItems = readOnly
                    ? profile.items.filter((item) => selectedItemIds.has(item.id))
                    : profile.items;
                  const canNavigateProfile =
                    readOnly && selectedCount > 0 && Boolean(onNavigateToProfile);
                  const ProfileIcon = getProfileIcon(profile.layer);
                  const profileSummary = profileSummaries.get(profile.id);
                  const profileDelta = profileDeltaCounts.get(profile.id);
                  const hasProfileDelta =
                    !readOnly &&
                    Boolean(profileDelta && (profileDelta.added > 0 || profileDelta.removed > 0));
                  const profileDeltaText = profileDelta
                    ? [
                        profileDelta.added > 0 ? `+${profileDelta.added}` : null,
                        profileDelta.removed > 0 ? `-${profileDelta.removed}` : null,
                      ]
                        .filter(Boolean)
                        .join('/')
                    : '';

                  return (
                    <div
                      key={profile.id}
                      className={`rounded-lg transition-colors ${
                        !readOnly && isFocused
                          ? 'border border-system-blue/35 bg-system-blue/10 shadow-sm'
                          : someSelected || isExpanded
                            ? 'border border-border-black bg-panel-bg'
                            : 'border border-transparent hover:border-border-black hover:bg-element-hover'
                      }`}
                    >
                      <div className="flex items-start gap-2 p-2">
                        {readOnly || isNavigationOnly ? (
                          <div
                            aria-hidden="true"
                            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                              hasProfileDelta
                                ? 'bg-warning'
                                : isFocused
                                  ? 'bg-system-blue shadow-[0_0_0_4px_rgba(0,122,255,0.10)]'
                                  : someSelected
                                    ? 'bg-system-blue'
                                    : 'bg-border-strong'
                            }`}
                          />
                        ) : (
                          <button
                            type="button"
                            aria-label={profileName}
                            disabled={isInteractionLocked}
                            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                              isGeneratingAI
                                ? 'border-border-strong bg-element-bg'
                                : allSelected
                                  ? 'border-system-blue-solid bg-system-blue-solid'
                                  : someSelected
                                    ? 'border-system-blue bg-system-blue/80'
                                    : 'border-border-strong bg-panel-bg hover:border-system-blue'
                            }`}
                            onClick={() => {
                              toggleProfileSelection(profile.id);
                              onFocusProfile(profile.id);
                            }}
                          >
                            {allSelected ? (
                              <Check className="h-3 w-3 text-white" />
                            ) : someSelected ? (
                              <Minus className="h-2.5 w-2.5 text-white" />
                            ) : null}
                          </button>
                        )}

                        <div className="min-w-0 flex-1">
                          {readOnly && canNavigateProfile ? (
                            <button
                              type="button"
                              disabled={isInteractionLocked}
                              className="w-full rounded-lg text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30"
                              onClick={() => {
                                onFocusProfile(profile.id);
                                onNavigateToProfile?.(profile.id);
                              }}
                            >
                              <div className="flex items-center gap-2">
                                <ProfileIcon className="h-3.5 w-3.5 shrink-0 text-system-blue" />
                                <span className="truncate text-xs font-semibold text-text-primary">
                                  {profileName}
                                </span>
                              </div>
                              <div className="mt-1 flex items-center gap-1.5 text-[10px] font-medium text-text-tertiary">
                                <span>
                                  {selectedCount}/{profile.items.length}
                                </span>
                                {hasProfileDelta && (
                                  <>
                                    <span aria-hidden="true">•</span>
                                    <span
                                      data-inspection-profile-delta={profile.id}
                                      title={`${t.inspectionUserAddedToRecommendation}: ${
                                        profileDelta?.added ?? 0
                                      }; ${t.inspectionUserRemovedFromRecommendation}: ${
                                        profileDelta?.removed ?? 0
                                      }`}
                                      className="rounded border border-border-black bg-element-bg px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-text-secondary"
                                    >
                                      {profileDeltaText}
                                    </span>
                                  </>
                                )}
                                {profileSummary && profileSummary.recommendedItemCount > 0 && (
                                  <>
                                    <span aria-hidden="true">•</span>
                                    <span>{t.inspectionRecommendedPlan}</span>
                                  </>
                                )}
                              </div>
                            </button>
                          ) : (
                            <button
                              type="button"
                              disabled={isInteractionLocked}
                              className="w-full text-left"
                              onClick={() => onFocusProfile(profile.id)}
                            >
                              <div className="flex items-center gap-2">
                                <ProfileIcon className="h-3.5 w-3.5 shrink-0 text-system-blue" />
                                <span className="truncate text-xs font-semibold text-text-primary">
                                  {profileName}
                                </span>
                              </div>
                              <div className="mt-1 flex items-center gap-1.5 text-[10px] font-medium text-text-tertiary">
                                <span>
                                  {selectedCount}/{profile.items.length}
                                </span>
                                {hasProfileDelta && (
                                  <>
                                    <span aria-hidden="true">•</span>
                                    <span
                                      data-inspection-profile-delta={profile.id}
                                      title={`${t.inspectionUserAddedToRecommendation}: ${
                                        profileDelta?.added ?? 0
                                      }; ${t.inspectionUserRemovedFromRecommendation}: ${
                                        profileDelta?.removed ?? 0
                                      }`}
                                      className="rounded border border-border-black bg-element-bg px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-text-secondary"
                                    >
                                      {profileDeltaText}
                                    </span>
                                  </>
                                )}
                                {profileSummary && profileSummary.recommendedItemCount > 0 && (
                                  <>
                                    <span aria-hidden="true">•</span>
                                    <span>{t.inspectionRecommendedPlan}</span>
                                  </>
                                )}
                              </div>
                            </button>
                          )}
                        </div>

                        {!isNavigationOnly && (
                          <button
                            type="button"
                            disabled={isInteractionLocked}
                            className="rounded-md p-1 transition-colors hover:bg-element-hover disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent"
                            onClick={() => {
                              onFocusProfile(profile.id);
                              toggleProfileExpand(profile.id);
                            }}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-3.5 w-3.5 text-text-tertiary" />
                            ) : (
                              <ChevronRight className="h-3.5 w-3.5 text-text-tertiary" />
                            )}
                          </button>
                        )}
                      </div>

                      {!isNavigationOnly && isExpanded && (
                        <div
                          data-inspection-sidebar-item-list
                          className="animate-in fade-in slide-in-from-top-1 border-t border-border-black/80 px-2 pb-2 pt-2 duration-200"
                        >
                          <div className="space-y-1">
                            {visibleItems.map((item) => {
                              const isSelected = selectedItemIds.has(item.id);
                              const itemName = lang === 'zh' ? item.nameZh : item.name;

                              if (readOnly) {
                                const canNavigateItem = isSelected && Boolean(onNavigateToItem);

                                if (canNavigateItem) {
                                  return (
                                    <button
                                      key={item.id}
                                      type="button"
                                      disabled={isInteractionLocked}
                                      className="flex w-full items-center gap-2 rounded-lg bg-element-bg px-1.5 py-1.5 text-left transition-colors hover:bg-element-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30"
                                      onClick={() => {
                                        onFocusProfile(profile.id);
                                        onNavigateToItem?.(profile.id, item.id);
                                      }}
                                    >
                                      <div
                                        aria-hidden="true"
                                        className="h-2 w-2 shrink-0 rounded-full bg-system-blue"
                                      />
                                      <span className="truncate text-[11px] font-medium text-text-secondary">
                                        {itemName}
                                      </span>
                                    </button>
                                  );
                                }

                                return (
                                  <div
                                    key={item.id}
                                    className={`flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 ${
                                      isSelected ? 'bg-element-bg' : 'bg-transparent'
                                    }`}
                                  >
                                    <div
                                      aria-hidden="true"
                                      className={`h-2 w-2 shrink-0 rounded-full ${
                                        isSelected ? 'bg-system-blue' : 'bg-border-strong'
                                      }`}
                                    />
                                    <span
                                      className={`truncate text-[11px] font-medium ${
                                        isSelected ? 'text-text-secondary' : 'text-text-tertiary'
                                      }`}
                                    >
                                      {itemName}
                                    </span>
                                  </div>
                                );
                              }

                              return (
                                <div
                                  key={item.id}
                                  className={`flex w-full items-center gap-2 rounded-lg p-1.5 text-left transition-colors ${
                                    isSelected ? 'bg-element-bg' : 'hover:bg-element-hover'
                                  }`}
                                >
                                  <button
                                    type="button"
                                    aria-label={itemName}
                                    disabled={isInteractionLocked}
                                    className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded border transition-colors ${
                                      isSelected
                                        ? 'border-system-blue-solid bg-system-blue-solid'
                                        : 'border-border-strong bg-panel-bg'
                                    }`}
                                    onClick={() => {
                                      toggleItemSelection(profile.id, item.id);
                                      onFocusProfile(profile.id);
                                    }}
                                  >
                                    {isSelected && <Check className="h-2.5 w-2.5 text-white" />}
                                  </button>
                                  <button
                                    type="button"
                                    data-inspection-sidebar-item-link={`${profile.id}:${item.id}`}
                                    disabled={isInteractionLocked}
                                    className="min-w-0 flex-1 truncate rounded-md text-left text-[11px] font-medium text-text-secondary transition-colors hover:text-system-blue focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-system-blue/30"
                                    onClick={() => {
                                      onFocusProfile(profile.id);
                                      onNavigateToSetupItem?.(profile.id, item.id);
                                    }}
                                  >
                                    {itemName}
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>}
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default InspectionSidebar;

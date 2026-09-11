import {
  INSPECTION_PROFILE_DEFINITIONS,
  getInspectionProfileDefinition,
  type InspectionProfileLayer,
} from '../config/inspectionProfiles'
import type { InspectionApplicabilityStatus } from './inspectionApplicability'
import type { SelectedInspectionProfiles } from './inspectionProfileSelection'

export interface InspectionSelectionDeltaItem {
  profileId: string
  itemId: string
}

export interface InspectionSelectionDeviation {
  addedItems: InspectionSelectionDeltaItem[]
  removedItems: InspectionSelectionDeltaItem[]
  changedProfileIds: string[]
  totalChangedItemCount: number
}

export interface InspectionLayerSummary {
  layer: InspectionProfileLayer
  selectedItemCount: number
  recommendedItemCount: number
  totalItemCount: number
  unavailableProfileCount: number
  insufficientEvidenceProfileCount: number
  profileIds: string[]
}

export type InspectionProfileScopeRelation =
  | 'recommended'
  | 'user_added'
  | 'user_removed'
  | 'unchanged_unselected'
  | 'partial'

export interface InspectionProfileScopeSummary {
  profileId: string
  layer: InspectionProfileLayer
  selectedItemCount: number
  recommendedItemCount: number
  totalItemCount: number
  applicability: InspectionApplicabilityStatus
  relation: InspectionProfileScopeRelation
}

export type InspectionItemScopeRelation =
  | 'recommended_included'
  | 'user_added'
  | 'user_removed'
  | 'not_recommended'
  | 'unavailable'

export interface InspectionItemScopeSummary {
  profileId: string
  itemId: string
  selected: boolean
  recommended: boolean
  applicability: InspectionApplicabilityStatus
  relation: InspectionItemScopeRelation
}

export type InspectionScopeApplicabilityResolver = (
  profileId: string,
  itemId?: string,
) => InspectionApplicabilityStatus

const LAYER_ORDER: InspectionProfileLayer[] = ['base', 'morph', 'format', 'target', 'workflow']

const defaultApplicabilityResolver: InspectionScopeApplicabilityResolver = () => 'applicable'

const getSelectedSet = (selectedProfiles: SelectedInspectionProfiles, profileId: string) =>
  selectedProfiles[profileId] ?? new Set<string>()

const areSetsEqual = (left: Set<string>, right: Set<string>) => {
  if (left.size !== right.size) {
    return false
  }

  for (const value of left) {
    if (!right.has(value)) {
      return false
    }
  }

  return true
}

const sortDeltaItems = (items: InspectionSelectionDeltaItem[]) =>
  items.sort((left, right) =>
    left.profileId === right.profileId
      ? left.itemId.localeCompare(right.itemId)
      : left.profileId.localeCompare(right.profileId),
  )

export function buildInspectionSelectionDeviation(
  selectedProfiles: SelectedInspectionProfiles,
  recommendedProfiles: SelectedInspectionProfiles,
): InspectionSelectionDeviation {
  const addedItems: InspectionSelectionDeltaItem[] = []
  const removedItems: InspectionSelectionDeltaItem[] = []
  const changedProfileIds = new Set<string>()
  const profileIds = new Set([
    ...Object.keys(selectedProfiles),
    ...Object.keys(recommendedProfiles),
  ])

  profileIds.forEach((profileId) => {
    const selectedItems = getSelectedSet(selectedProfiles, profileId)
    const recommendedItems = getSelectedSet(recommendedProfiles, profileId)

    selectedItems.forEach((itemId) => {
      if (!recommendedItems.has(itemId)) {
        addedItems.push({ profileId, itemId })
        changedProfileIds.add(profileId)
      }
    })

    recommendedItems.forEach((itemId) => {
      if (!selectedItems.has(itemId)) {
        removedItems.push({ profileId, itemId })
        changedProfileIds.add(profileId)
      }
    })
  })

  return {
    addedItems: sortDeltaItems(addedItems),
    removedItems: sortDeltaItems(removedItems),
    changedProfileIds: Array.from(changedProfileIds).sort(),
    totalChangedItemCount: addedItems.length + removedItems.length,
  }
}

export function buildInspectionLayerSummaries(
  selectedProfiles: SelectedInspectionProfiles,
  recommendedProfiles: SelectedInspectionProfiles,
  getApplicability: InspectionScopeApplicabilityResolver = defaultApplicabilityResolver,
): InspectionLayerSummary[] {
  return LAYER_ORDER.map((layer) => {
    const profiles = INSPECTION_PROFILE_DEFINITIONS.filter((profile) => profile.layer === layer)

    return profiles.reduce<InspectionLayerSummary>(
      (summary, profile) => {
        const applicability = getApplicability(profile.id)

        return {
          ...summary,
          selectedItemCount: summary.selectedItemCount + getSelectedSet(selectedProfiles, profile.id).size,
          recommendedItemCount:
            summary.recommendedItemCount + getSelectedSet(recommendedProfiles, profile.id).size,
          totalItemCount: summary.totalItemCount + profile.items.length,
          unavailableProfileCount:
            summary.unavailableProfileCount + (applicability === 'not_applicable' ? 1 : 0),
          insufficientEvidenceProfileCount:
            summary.insufficientEvidenceProfileCount +
            (applicability === 'insufficient_evidence' ? 1 : 0),
          profileIds: [...summary.profileIds, profile.id],
        }
      },
      {
        layer,
        selectedItemCount: 0,
        recommendedItemCount: 0,
        totalItemCount: 0,
        unavailableProfileCount: 0,
        insufficientEvidenceProfileCount: 0,
        profileIds: [],
      },
    )
  })
}

export function buildInspectionProfileScopeSummaries(
  selectedProfiles: SelectedInspectionProfiles,
  recommendedProfiles: SelectedInspectionProfiles,
  getApplicability: InspectionScopeApplicabilityResolver = defaultApplicabilityResolver,
): InspectionProfileScopeSummary[] {
  return INSPECTION_PROFILE_DEFINITIONS.map((profile) => {
    const selectedItems = getSelectedSet(selectedProfiles, profile.id)
    const recommendedItems = getSelectedSet(recommendedProfiles, profile.id)
    let relation: InspectionProfileScopeRelation = 'unchanged_unselected'

    if (selectedItems.size > 0 && recommendedItems.size === 0) {
      relation = 'user_added'
    } else if (selectedItems.size === 0 && recommendedItems.size > 0) {
      relation = 'user_removed'
    } else if (selectedItems.size > 0 && recommendedItems.size > 0) {
      relation = areSetsEqual(selectedItems, recommendedItems) ? 'recommended' : 'partial'
    }

    return {
      profileId: profile.id,
      layer: profile.layer,
      selectedItemCount: selectedItems.size,
      recommendedItemCount: recommendedItems.size,
      totalItemCount: profile.items.length,
      applicability: getApplicability(profile.id),
      relation,
    }
  })
}

export function buildInspectionItemScopeSummaries(
  profileId: string,
  selectedProfiles: SelectedInspectionProfiles,
  recommendedProfiles: SelectedInspectionProfiles,
  getApplicability: InspectionScopeApplicabilityResolver = defaultApplicabilityResolver,
): InspectionItemScopeSummary[] {
  const profile = getInspectionProfileDefinition(profileId)
  if (!profile) {
    return []
  }

  const selectedItems = getSelectedSet(selectedProfiles, profileId)
  const recommendedItems = getSelectedSet(recommendedProfiles, profileId)

  return profile.items.map((item) => {
    const selected = selectedItems.has(item.id)
    const recommended = recommendedItems.has(item.id)
    const applicability = getApplicability(profileId, item.id)
    let relation: InspectionItemScopeRelation = 'not_recommended'

    if (applicability !== 'applicable') {
      relation = 'unavailable'
    } else if (selected && recommended) {
      relation = 'recommended_included'
    } else if (selected && !recommended) {
      relation = 'user_added'
    } else if (!selected && recommended) {
      relation = 'user_removed'
    }

    return {
      profileId,
      itemId: item.id,
      selected,
      recommended,
      applicability,
      relation,
    }
  })
}

import type { RobotState } from '@/types'
import type { Language } from '@/shared/i18n'
import {
  buildInspectionEvidenceSummary,
  type InspectionEvidenceSummary,
} from '@/shared/utils/inspectionEvidenceSummary'
import { INSPECTION_PROFILE_DEFINITIONS } from '../config/inspectionProfiles'
import type { SelectedInspectionProfiles } from './inspectionProfileSelection'

export interface InspectionEstimatedDuration {
  label: string
  maxSeconds: number
}

export interface InspectionRunProfileSummary {
  id: string
  name: string
  selectedCount: number
  totalCount: number
}

export interface InspectionRunContext {
  robotName: string
  sourceValue: string
  linkCount: number
  jointCount: number
  selectedCount: number
  selectedProfileCount: number
  estimatedDuration: InspectionEstimatedDuration
  profileSummary: InspectionRunProfileSummary[]
  evidenceSummary: InspectionEvidenceSummary | null
}

export function estimateInspectionDuration(
  robot: RobotState,
  selectedCount: number,
): InspectionEstimatedDuration {
  let complexity = Object.keys(robot.links).length + Object.keys(robot.joints).length + selectedCount * 2

  if (robot.inspectionContext?.sourceFormat === 'mjcf') {
    complexity += 6
  }

  if (complexity <= 35) {
    return { label: '10-20s', maxSeconds: 20 }
  }
  if (complexity <= 65) {
    return { label: '20-40s', maxSeconds: 40 }
  }
  return { label: '30-60s', maxSeconds: 60 }
}

export function buildInspectionRunContext(
  robot: RobotState,
  selectedItems: SelectedInspectionProfiles,
  lang: Language,
  normalizedModelLabel: string,
): InspectionRunContext {
  const profileSummary: InspectionRunProfileSummary[] = []
  let selectedCount = 0

  INSPECTION_PROFILE_DEFINITIONS.forEach((profile) => {
    const itemIds = selectedItems[profile.id] ?? new Set<string>()
    const count = itemIds.size

    if (count === 0) {
      return
    }

    selectedCount += count
    profileSummary.push({
      id: profile.id,
      name: lang === 'zh' ? profile.nameZh : profile.name,
      selectedCount: count,
      totalCount: profile.items.length,
    })
  })

  return {
    robotName: robot.name || '-',
    sourceValue: robot.inspectionContext?.sourceFormat?.toUpperCase() ?? normalizedModelLabel,
    linkCount: Object.keys(robot.links).length,
    jointCount: Object.keys(robot.joints).length,
    selectedCount,
    selectedProfileCount: profileSummary.length,
    estimatedDuration: estimateInspectionDuration(robot, selectedCount),
    profileSummary,
    evidenceSummary: buildInspectionEvidenceSummary(robot.inspectionContext, lang),
  }
}

import type { InspectionReport } from '@/types'
import { translations } from '@/shared/i18n'
import type { IssueType } from '../types'
import {
  getInspectionProfileDefinition,
  getInspectionProfileItem,
} from '../config/inspectionProfiles'
import {
  createProfileScoreMetrics,
  type SelectedInspectionProfileMap,
} from './inspectionProfileSelection'

interface ParsedInspectionResult {
  summary?: string
  issues?: unknown[]
}

interface RawInspectionIssue extends Record<string, unknown> {
  type?: IssueType
  title?: string
  description?: string
  profileId?: string
  itemId?: string
  evidenceLevel?: 'L1' | 'L2' | 'L3' | 'L4'
  evidenceSource?: string
  score?: number
  relatedIds?: string[]
}

const VALID_ISSUE_TYPES = new Set<IssueType>(['error', 'warning', 'suggestion', 'pass'])

const scoreForIssueType = (type: IssueType, hasExplicitIssue: boolean) => {
  if (!hasExplicitIssue || type === 'pass') {
    return 10
  }
  if (type === 'error') {
    return 2
  }
  if (type === 'warning') {
    return 5
  }
  return 8
}

const normalizeIssueType = (type: unknown): IssueType => {
  return typeof type === 'string' && VALID_ISSUE_TYPES.has(type as IssueType)
    ? (type as IssueType)
    : 'suggestion'
}

const toRelatedIds = (relatedIds: unknown) => {
  if (!Array.isArray(relatedIds)) {
    return undefined
  }

  const ids = relatedIds
    .map((id) => (typeof id === 'string' ? id.trim() : ''))
    .filter(Boolean)

  return ids.length > 0 ? ids : undefined
}

const createUnmappedIssue = (
  rawIssue: RawInspectionIssue,
  lang: 'en' | 'zh',
): InspectionReport['issues'][number] => {
  const t = translations[lang]
  const rawTitle = typeof rawIssue.title === 'string' ? rawIssue.title : ''
  const rawDescription = typeof rawIssue.description === 'string' ? rawIssue.description : ''

  return {
    type: 'error',
    title: t.inspectionUnmappedIssueTitle,
    description: t.inspectionUnmappedIssueDescription
      .replace('{title}', rawTitle || t.none)
      .replace('{description}', rawDescription || t.none),
    profileId: 'unmapped',
    itemId: 'unmapped',
    evidenceLevel: 'L3',
    evidenceSource: 'ai_inference',
    relatedIds: toRelatedIds(rawIssue.relatedIds),
    score: 0,
  }
}

const normalizeIssue = (
  rawIssue: RawInspectionIssue,
  lang: 'en' | 'zh',
): InspectionReport['issues'][number] => {
  const profileId = typeof rawIssue.profileId === 'string' ? rawIssue.profileId : ''
  const itemId = typeof rawIssue.itemId === 'string' ? rawIssue.itemId : ''

  if (!profileId || !itemId || !getInspectionProfileItem(profileId, itemId)) {
    return createUnmappedIssue(rawIssue, lang)
  }

  const type = normalizeIssueType(rawIssue.type)
  const profile = getInspectionProfileDefinition(profileId)
  const item = getInspectionProfileItem(profileId, itemId)
  const score =
    typeof rawIssue.score === 'number' ? rawIssue.score : scoreForIssueType(type, type !== 'pass')

  return {
    type,
    title:
      typeof rawIssue.title === 'string' && rawIssue.title.trim()
        ? rawIssue.title
        : `${profile?.name ?? profileId}: ${item?.name ?? itemId}`,
    description:
      typeof rawIssue.description === 'string' && rawIssue.description.trim()
        ? rawIssue.description
        : (item?.description ?? itemId),
    profileId,
    itemId,
    evidenceLevel: rawIssue.evidenceLevel,
    evidenceSource:
      typeof rawIssue.evidenceSource === 'string' ? rawIssue.evidenceSource : 'ai_inference',
    relatedIds: toRelatedIds(rawIssue.relatedIds),
    score,
  }
}

const issueMatchesSelectedScope = (
  issue: InspectionReport['issues'][number],
  selectedProfiles?: SelectedInspectionProfileMap,
) => {
  if (!selectedProfiles || issue.profileId === 'unmapped' || issue.itemId === 'unmapped') {
    return true
  }

  return selectedProfiles[issue.profileId]?.includes(issue.itemId) ?? false
}

export function processInspectionResults(
  rawResults: unknown,
  selectedProfiles?: SelectedInspectionProfileMap,
  lang: 'en' | 'zh' = 'en',
): InspectionReport {
  const t = translations[lang]
  const parsedResult = (rawResults || {}) as ParsedInspectionResult
  const issues = ((parsedResult.issues || []) as RawInspectionIssue[])
    .map((rawIssue) => normalizeIssue({ ...rawIssue }, lang))
    .filter((issue) => issueMatchesSelectedScope(issue, selectedProfiles))
  const allIssues: InspectionReport['issues'] = [...issues]
  const reportedItems = new Set(issues.map((issue) => `${issue.profileId}:${issue.itemId}`))

  Object.entries(selectedProfiles ?? {}).forEach(([profileId, itemIds]) => {
    itemIds.forEach((itemId) => {
      const key = `${profileId}:${itemId}`
      if (reportedItems.has(key)) {
        return
      }

      const item = getInspectionProfileItem(profileId, itemId)
      if (!item) {
        return
      }

      const itemName = lang === 'zh' ? item.nameZh : item.name
      const itemDesc = lang === 'zh' ? item.descriptionZh : item.description
      allIssues.push({
        type: 'pass',
        title: t.inspectionPassTitle.replace('{itemName}', itemName),
        description: t.inspectionPassDescription.replace('{itemDesc}', itemDesc),
        profileId,
        itemId,
        evidenceSource: 'ai_inference',
        score: 10,
      })
    })
  })

  return {
    summary: parsedResult.summary || t.inspectionCompleted,
    issues: allIssues,
    ...createProfileScoreMetrics(allIssues),
  }
}

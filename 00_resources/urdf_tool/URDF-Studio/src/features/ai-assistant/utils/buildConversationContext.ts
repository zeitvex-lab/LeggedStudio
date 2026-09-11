import type { InspectionReport, RobotState } from '@/types'
import type { ConversationMode } from '../config/prompts'
import type { AIConversationFocusedIssue, AIConversationSelection } from '../types'

export interface ConversationContextOptions {
  mode: ConversationMode
  robot: RobotState
  inspectionReport?: InspectionReport | null
  selectedEntity?: AIConversationSelection | null
  focusedIssue?: AIConversationFocusedIssue | null
}

const toSortedStringArray = (values: string[] | undefined): string[] | undefined => {
  if (!values || values.length === 0) return undefined
  return [...values].sort((a, b) => a.localeCompare(b))
}

export const buildConversationContext = ({
  mode,
  robot,
  inspectionReport,
  selectedEntity = null,
  focusedIssue = null,
}: ConversationContextOptions): string => {
  const selectedSnapshotEntityId = selectedEntity
    ? (selectedEntity.snapshotEntityId ?? selectedEntity.entityId)
    : null
  const selectedEntitySnapshot = selectedEntity && selectedSnapshotEntityId
    ? {
        type: selectedEntity.type,
        componentId: selectedEntity.componentId,
        entityId: selectedEntity.entityId,
        name: selectedEntity.type === 'link'
          ? robot.links[selectedSnapshotEntityId]?.name || selectedEntity.entityId
          : robot.joints[selectedSnapshotEntityId]?.name || selectedEntity.entityId,
      }
    : undefined

  const robotSnapshot = {
    name: robot.name,
    rootLinkId: robot.rootLinkId,
    linkCount: Object.keys(robot.links).length,
    jointCount: Object.keys(robot.joints).length,
    links: Object.values(robot.links).map(link => ({
      id: link.id,
      name: link.name,
      visualType: link.visual.type,
      collisionType: link.collision.type,
      mass: link.inertial?.mass,
    })),
    joints: Object.values(robot.joints).map(joint => ({
      id: joint.id,
      name: joint.name,
      type: joint.type,
      parent: joint.parentLinkId,
      child: joint.childLinkId,
      axis: joint.axis,
      limit: joint.limit,
      hardware: joint.hardware
        ? {
            motorType: joint.hardware.motorType,
            armature: joint.hardware.armature,
            motorDirection: joint.hardware.motorDirection,
          }
        : undefined,
    })),
    inspectionContext: robot.inspectionContext,
  }

  const reportSnapshot = inspectionReport
    ? {
        summary: inspectionReport.summary,
        overallScore: inspectionReport.overallScore,
        maxScore: inspectionReport.maxScore,
        profileScores: inspectionReport.profileScores,
        issues: inspectionReport.issues.map(issue => ({
          type: issue.type,
          title: issue.title,
          description: issue.description,
          profileId: issue.profileId,
          itemId: issue.itemId,
          evidenceLevel: issue.evidenceLevel,
          evidenceSource: issue.evidenceSource,
          score: issue.score,
          relatedIds: toSortedStringArray(issue.relatedIds),
        })),
      }
    : null

  const payload = {
    mode,
    robot: robotSnapshot,
    inspectionReport: reportSnapshot || undefined,
    selectedEntity: selectedEntitySnapshot,
    focusedIssue: focusedIssue
      ? {
          type: focusedIssue.type,
          title: focusedIssue.title,
          description: focusedIssue.description,
          profileId: focusedIssue.profileId,
          itemId: focusedIssue.itemId,
          evidenceLevel: focusedIssue.evidenceLevel,
          evidenceSource: focusedIssue.evidenceSource,
          score: focusedIssue.score,
          relatedIds: toSortedStringArray(focusedIssue.relatedIds),
        }
      : undefined,
  }

  return JSON.stringify(payload, null, 2)
}

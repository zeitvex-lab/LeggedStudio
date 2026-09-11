import type { InspectionReport, RobotState } from '@/types';

export interface InspectionIssueSelectionTarget {
  type: 'link' | 'joint';
  id: string;
}

export interface InspectionIssueRelatedEntity {
  id: string;
  name: string;
  target: InspectionIssueSelectionTarget | null;
}

export function resolveInspectionIssueRelatedEntities(
  robot: RobotState,
  issue: InspectionReport['issues'][number],
): InspectionIssueRelatedEntity[] {
  const entities: InspectionIssueRelatedEntity[] = [];
  const seenIds = new Set<string>();

  for (const rawId of issue.relatedIds || []) {
    const id = typeof rawId === 'string' ? rawId.trim() : '';
    if (!id || seenIds.has(id)) {
      continue;
    }

    seenIds.add(id);

    if (robot.links[id]) {
      entities.push({
        id,
        name: robot.links[id].name || id,
        target: {
          type: 'link',
          id,
        },
      });
      continue;
    }

    if (robot.joints[id]) {
      entities.push({
        id,
        name: robot.joints[id].name || id,
        target: {
          type: 'joint',
          id,
        },
      });
      continue;
    }

    entities.push({
      id,
      name: id,
      target: null,
    });
  }

  return entities;
}

export function resolveInspectionIssueSelectionTarget(
  robot: RobotState,
  issue: InspectionReport['issues'][number],
): InspectionIssueSelectionTarget | null {
  return (
    resolveInspectionIssueRelatedEntities(robot, issue).find((entity) => entity.target)?.target ??
    null
  );
}

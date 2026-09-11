import React, { useEffect, useMemo, useState } from 'react';
import { Waypoints } from 'lucide-react';
import { getChildJointsByParentLink, getParentJointByChildLink } from '@/core/robot';
import { JointType, type AppMode, type MotorSpec, type RobotState, type UrdfJoint } from '@/types';
import { translations } from '@/shared/i18n';
import {
  getMjcfJointDisplayName,
  getMjcfLinkDisplayName,
} from '@/shared/utils/robot/mjcfDisplayNames';
import type { Language } from '@/store/uiStore';
import { JointProperties } from './JointProperties';

type RelatedJointEntry = { joint: UrdfJoint };

interface LinkJointEditorProps {
  linkId: string;
  robot: RobotState;
  mode: AppMode;
  motorLibrary: Record<string, MotorSpec[]>;
  onUpdate: (type: 'link' | 'joint', id: string, data: unknown) => void;
  t: (typeof translations)['en'];
  lang: Language;
}

export const LinkJointEditor: React.FC<LinkJointEditorProps> = ({
  linkId,
  robot,
  mode,
  motorLibrary,
  onUpdate,
  t,
  lang,
}) => {
  const sourceFormat = robot.inspectionContext?.sourceFormat;
  const linkDisplayNames = useMemo<Record<string, string>>(
    () =>
      Object.fromEntries(
        Object.values(robot.links).map((link) => [
          link.id,
          sourceFormat === 'mjcf' ? getMjcfLinkDisplayName(link) : link.name,
        ]),
      ),
    [robot.links, sourceFormat],
  );
  const relatedJoints = useMemo<RelatedJointEntry[]>(() => {
    const childJoints = getChildJointsByParentLink(robot).get(linkId) ?? [];
    const parentJoint = getParentJointByChildLink(robot).get(linkId);
    const prioritizedChildJoints = [
      ...childJoints.filter((joint) => joint.type !== JointType.FIXED),
      ...childJoints.filter((joint) => joint.type === JointType.FIXED),
    ];

    return [
      ...prioritizedChildJoints.map((joint) => ({ joint })),
      ...(parentJoint ? [{ joint: parentJoint }] : []),
    ];
  }, [linkId, robot]);

  const [activeJointId, setActiveJointId] = useState<string | null>(
    relatedJoints[0]?.joint.id ?? null,
  );

  useEffect(() => {
    if (relatedJoints.length === 0) {
      setActiveJointId(null);
      return;
    }

    if (!activeJointId || !relatedJoints.some((entry) => entry.joint.id === activeJointId)) {
      setActiveJointId(relatedJoints[0]?.joint.id ?? null);
    }
  }, [activeJointId, relatedJoints]);

  const activeJointEntry = relatedJoints.find((entry) => entry.joint.id === activeJointId) ?? null;

  if (relatedJoints.length === 0) {
    return (
      <div className="rounded-lg border border-border-black bg-panel-bg px-3 py-4 text-center text-[11px] text-text-tertiary">
        {t.noLinkedJoints}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {relatedJoints.length > 1 ? (
        <div className="rounded-lg border border-border-black bg-panel-bg p-1.5 shadow-sm">
          <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[10px] font-semibold tracking-[0.02em] text-text-tertiary">
            <Waypoints className="h-3.5 w-3.5 text-system-blue" />
            <span>{t.joints}</span>
          </div>
          <div className="flex flex-wrap gap-1">
            {relatedJoints.map((entry) => {
              const isActive = entry.joint.id === activeJointId;
              const jointDisplayName =
                sourceFormat === 'mjcf'
                  ? getMjcfJointDisplayName(
                      entry.joint,
                      linkDisplayNames[entry.joint.parentLinkId] || entry.joint.parentLinkId,
                      linkDisplayNames[entry.joint.childLinkId] || entry.joint.childLinkId,
                    )
                  : entry.joint.name || entry.joint.id;

              return (
                <button
                  key={entry.joint.id}
                  type="button"
                  onClick={() => setActiveJointId(entry.joint.id)}
                  className={`inline-flex min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-[10px] font-semibold transition-colors ${
                    isActive
                      ? 'border-system-blue/25 bg-system-blue/10 text-system-blue'
                      : 'border-border-black bg-element-bg text-text-secondary hover:bg-element-hover hover:text-text-primary'
                  }`}
                >
                  <span className="max-w-48 truncate text-left">{jointDisplayName}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}

      {activeJointEntry ? (
        <JointProperties
          data={activeJointEntry.joint}
          mode={mode}
          selection={{ type: 'joint', id: activeJointEntry.joint.id }}
          onUpdate={onUpdate}
          motorLibrary={motorLibrary}
          t={t}
          lang={lang}
        />
      ) : null}
    </div>
  );
};

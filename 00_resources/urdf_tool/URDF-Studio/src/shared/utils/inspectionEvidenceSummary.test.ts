import test from 'node:test';
import assert from 'node:assert/strict';

import type { RobotInspectionContext } from '@/types';
import { buildInspectionEvidenceSummary } from './inspectionEvidenceSummary.ts';

test('buildInspectionEvidenceSummary exposes MJCF source evidence metrics', () => {
  const inspectionContext: RobotInspectionContext = {
    sourceFormat: 'mjcf',
    mjcf: {
      siteCount: 2,
      tendonCount: 1,
      tendonActuatorCount: 1,
      bodiesWithSites: [
        { bodyId: 'base_link', siteCount: 2, siteNames: ['tip_site', 'frame_site'] },
      ],
      tendons: [
        {
          name: 'finger_tendon',
          type: 'spatial',
          attachmentRefs: ['tip_site', 'frame_site'],
          attachments: [
            { type: 'site', ref: 'tip_site' },
            { type: 'site', ref: 'frame_site' },
          ],
          actuatorNames: ['finger_motor'],
        },
      ],
    },
  };

  const summary = buildInspectionEvidenceSummary(inspectionContext, 'en');

  assert.ok(summary);
  assert.equal(summary.title, 'Source Evidence');
  assert.deepEqual(summary.metrics, [
    { label: 'Source', value: 'MJCF' },
    { label: 'Bodies with Sites', value: '1' },
    { label: 'Sites', value: '2' },
    { label: 'Tendons', value: '1' },
    { label: 'Tendon Actuators', value: '1' },
  ]);
});

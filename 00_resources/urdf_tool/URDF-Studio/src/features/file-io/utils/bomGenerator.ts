/**
 * BOM (Bill of Materials) Generator
 * Generate CSV format BOM from robot state
 */

import type { RobotState } from '@/types';
import type { Language } from '@/store';
import { translations } from '@/shared/i18n';

/**
 * Generate BOM CSV string from robot state
 * @param robot - Robot state with joints and hardware info
 * @param lang - Language for headers (zh or en)
 * @returns CSV formatted string
 */
export function generateBOM(robot: RobotState, lang: Language = 'en'): string {
  const t = translations[lang];
  const headers = [t.jointName, t.type, t.motorType, t.motorId, t.direction, t.armature, t.lower, t.upper];

  const rows = Object.values(robot.joints).map(j => {
    if (j.type === 'fixed') return null;
    // Skip if motor type is None or empty
    if (!j.hardware?.motorType || j.hardware.motorType === 'None') return null;

    return [
      j.name,
      j.type,
      j.hardware?.motorType,
      j.hardware?.motorId || '',
      j.hardware?.motorDirection || 1,
      j.hardware?.armature || 0,
      j.limit?.lower ?? '',
      j.limit?.upper ?? ''
    ].join(',');
  }).filter(row => row !== null);

  return [headers.join(','), ...rows].join('\n');
}

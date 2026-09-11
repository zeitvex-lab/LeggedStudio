import type { RobotInspectionContext } from '@/types'
import { translations } from '@/shared/i18n'

export interface InspectionEvidenceMetric {
  label: string
  value: string
}

export interface InspectionEvidenceSummary {
  title: string
  metrics: InspectionEvidenceMetric[]
}

export function buildInspectionEvidenceSummary(
  inspectionContext: RobotInspectionContext | undefined,
  lang: 'en' | 'zh'
): InspectionEvidenceSummary | null {
  if (!inspectionContext) {
    return null
  }

  const t = translations[lang]
  const metrics: InspectionEvidenceMetric[] = [
    {
      label: t.inspectionEvidenceSourceFormat,
      value: inspectionContext.sourceFormat.toUpperCase()
    }
  ]

  if (inspectionContext.sourceFormat === 'mjcf' && inspectionContext.mjcf) {
    metrics.push(
      {
        label: t.inspectionEvidenceBodiesWithSites,
        value: String(inspectionContext.mjcf.bodiesWithSites.length)
      },
      {
        label: t.inspectionEvidenceSites,
        value: String(inspectionContext.mjcf.siteCount)
      },
      {
        label: t.inspectionEvidenceTendons,
        value: String(inspectionContext.mjcf.tendonCount)
      },
      {
        label: t.inspectionEvidenceTendonActuators,
        value: String(inspectionContext.mjcf.tendonActuatorCount)
      }
    )
  }

  return {
    title: t.inspectionEvidenceTitle,
    metrics
  }
}

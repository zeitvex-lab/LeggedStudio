import { exportInspectionReportPdf as exportSharedInspectionReportPdf } from '@/shared/utils/reports/inspectionReportPdfExport'
import type { Language } from '@/shared/i18n'
import type { InspectionReport, RobotInspectionContext } from '@/types'
import { getInspectionProfileName } from '../config/inspectionProfiles'

interface ExportInspectionReportPdfParams {
  inspectionReport: InspectionReport | null
  robotName: string
  lang: Language
  inspectionContext?: RobotInspectionContext
}

export function exportInspectionReportPdf({
  inspectionReport,
  robotName,
  lang,
  inspectionContext
}: ExportInspectionReportPdfParams): Promise<void> {
  const profileLabels = inspectionReport
    ? Object.fromEntries(
        Array.from(new Set(inspectionReport.issues.map(issue => issue.profileId).filter(Boolean))).map(
          profileId => [profileId, getInspectionProfileName(profileId as string, lang)]
        )
      )
    : {}

  return exportSharedInspectionReportPdf({
    inspectionReport,
    robotName,
    lang,
    inspectionContext,
    profileLabels
  })
}

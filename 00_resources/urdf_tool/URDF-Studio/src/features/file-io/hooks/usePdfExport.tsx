import { useCallback, useMemo } from 'react';
import { resolveWorkspaceRobotDataTarget } from '@/core/robot';
import { useUIStore } from '@/store';
import { useSelectionStore } from '@/store/selectionStore';
import { useWorkspaceStore } from '@/store/workspaceStore';
import type { InspectionReport } from '@/types';
import { exportInspectionReportPdf } from '@/shared/utils/reports/inspectionReportPdfExport';

interface UsePdfExportReturn {
  handleDownloadPDF: (inspectionReport: InspectionReport | null) => void;
}

export function usePdfExport(): UsePdfExportReturn {
  const lang = useUIStore((s) => s.lang);
  const workspace = useWorkspaceStore((state) => state.workspace);
  const selection = useSelectionStore((state) => state.selection);
  const robot = useMemo(
    () => resolveWorkspaceRobotDataTarget(workspace, selection).robotData,
    [selection, workspace],
  );

  const handleDownloadPDF = useCallback((inspectionReport: InspectionReport | null) => {
    void exportInspectionReportPdf({
      inspectionReport,
      robotName: robot.name,
      lang,
      inspectionContext: robot.inspectionContext,
    }).catch((error) => {
      console.error('Inspection report PDF export failed', error);
    });
  }, [lang, robot]);

  return {
    handleDownloadPDF,
  };
}

import { createElement } from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';

import { InspectionReportTemplate } from '@/shared/components/reports/InspectionReportTemplate';
import { translations, type Language } from '@/shared/i18n';
import type { InspectionReport, RobotInspectionContext } from '@/types';
import { printElementAsPdf } from '@/shared/utils/pdf/printElementAsPdf';

const REPORT_CONTAINER_ID = 'inspection-report-pdf-export-container';

interface ExportInspectionReportPdfParams {
  inspectionReport: InspectionReport | null;
  robotName: string;
  lang: Language;
  inspectionContext?: RobotInspectionContext;
  profileLabels?: Record<string, string>;
}

function buildInspectionReportPdfFileName(robotName: string, lang: Language): string {
  const t = translations[lang];
  const now = new Date();
  const dateStr = now.toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });

  return `${robotName}_${t.inspectionReportFileSuffix}_${dateStr.replace(/[\/\s:]/g, '_')}.pdf`;
}

function createHiddenPdfContainer(): HTMLDivElement {
  const container = document.createElement('div');
  container.id = REPORT_CONTAINER_ID;
  container.style.cssText = `
    position: fixed;
    left: -200vw;
    top: 0;
    width: 210mm;
    padding: 0;
    margin: 0;
    opacity: 0;
    pointer-events: none;
    background: #ffffff;
  `;
  document.body.appendChild(container);
  return container;
}

export async function exportInspectionReportPdf({
  inspectionReport,
  robotName,
  lang,
  inspectionContext,
  profileLabels,
}: ExportInspectionReportPdfParams): Promise<void> {
  if (!inspectionReport) {
    return;
  }

  const container = createHiddenPdfContainer();
  const root = createRoot(container);
  const fileName = buildInspectionReportPdfFileName(robotName, lang);

  try {
    flushSync(() => {
      root.render(
        createElement(InspectionReportTemplate, {
          inspectionReport,
          robotName,
          lang: lang as 'zh' | 'en',
          inspectionContext,
          profileLabels,
        }),
      );
    });

    const element = container.firstElementChild;
    if (!element) {
      throw new Error('Inspection report PDF element was not rendered');
    }

    await printElementAsPdf({
      element: element as HTMLElement,
      title: fileName,
    });
  } finally {
    flushSync(() => {
      root.unmount();
    });

    container.parentElement?.removeChild(container);
  }
}

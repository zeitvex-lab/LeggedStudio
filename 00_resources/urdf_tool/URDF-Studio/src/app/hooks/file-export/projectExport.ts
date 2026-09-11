import { exportProjectWithWorker } from '@/features/file-io';
import type { ExportProjectParams } from '@/features/file-io';
import { translations } from '@/shared/i18n';

import type {
  HandleProjectExportOptions,
  ProjectExportExecutionResult,
} from './types';
import type { ExportProgressReporter } from './progress';

type ExportTranslations = typeof translations.en;

interface ExecuteProjectExportParams {
  options?: HandleProjectExportOptions;
  name: string;
  lang: ExportProjectParams['lang'];
  workspace: ExportProjectParams['workspace'];
  workspaceHistory: ExportProjectParams['workspaceHistory'];
  componentSourceDrafts: NonNullable<ExportProjectParams['componentSourceDrafts']>;
  assets: ExportProjectParams['assets'];
  derivedCaches?: ExportProjectParams['derivedCaches'];
  createProgressReporter: (
    onProgress: HandleProjectExportOptions['onProgress'],
    totalSteps: number,
  ) => ExportProgressReporter;
  downloadBlob: (blob: Blob, fileName: string) => void;
  replaceTemplate: (template: string, replacements: Record<string, string | number>) => string;
  t: ExportTranslations;
  markAllSaved: () => void;
  isPersistenceSnapshotCurrent: () => boolean;
  archiveProject?: typeof exportProjectWithWorker;
}

export async function executeProjectExport({
  options = {},
  name,
  lang,
  workspace,
  workspaceHistory,
  componentSourceDrafts,
  assets,
  derivedCaches,
  createProgressReporter,
  downloadBlob,
  replaceTemplate,
  t,
  markAllSaved,
  isPersistenceSnapshotCurrent,
  archiveProject = exportProjectWithWorker,
}: ExecuteProjectExportParams): Promise<ProjectExportExecutionResult> {
  const reportProgress = createProgressReporter(options.onProgress, 6);
  reportProgress(1, t.exportProgressPreparing, t.exportProgressPreparingDetail, {
    stageProgress: 0.18,
    indeterminate: true,
  });
  reportProgress(
    2,
    t.exportProgressPackingProjectAssets,
    t.exportProgressPackingProjectAssetsPreparingDetail,
    {
      stageProgress: 0.04,
      indeterminate: true,
    },
  );

  const projectName = name.trim() || workspace.name.trim() || 'my_project';
  const result = await archiveProject({
    name: projectName,
    lang,
    workspace,
    workspaceHistory,
    componentSourceDrafts,
    assets,
    derivedCaches,
    onProgress: (progress) => {
      switch (progress.phase) {
        case 'assets':
          reportProgress(
            2,
            t.exportProgressPackingProjectAssets,
            replaceTemplate(t.exportProgressPackingProjectAssetsDetail, {
              current: progress.completed,
              total: progress.total,
              file: progress.label || t.exportProgressArchiveFallbackFile,
            }),
            {
              stageProgress: progress.total > 0 ? progress.completed / progress.total : 1,
              indeterminate: false,
            },
          );
          break;
        case 'metadata':
          reportProgress(
            3,
            t.exportProgressWritingProjectData,
            replaceTemplate(t.exportProgressWritingProjectDataDetail, {
              current: progress.completed,
              total: progress.total,
              item: progress.label || 'manifest.json',
            }),
            {
              stageProgress: progress.total > 0 ? progress.completed / progress.total : 1,
              indeterminate: false,
            },
          );
          break;
        case 'components':
          reportProgress(
            4,
            t.exportProgressBundlingProjectComponents,
            replaceTemplate(t.exportProgressBundlingProjectComponentsDetail, {
              current: progress.completed,
              total: progress.total,
              item: progress.label || t.exportProgressArchiveFallbackFile,
            }),
            {
              stageProgress: progress.total > 0 ? progress.completed / progress.total : 1,
              indeterminate: false,
            },
          );
          break;
        case 'output':
          reportProgress(
            5,
            t.exportProgressGeneratingProjectOutputs,
            replaceTemplate(t.exportProgressGeneratingProjectOutputsDetail, {
              current: progress.completed,
              total: progress.total,
              item: progress.label || t.exportProgressArchiveFallbackFile,
            }),
            {
              stageProgress: progress.total > 0 ? progress.completed / progress.total : 1,
              indeterminate: false,
            },
          );
          break;
        case 'archive':
          reportProgress(
            6,
            t.exportProgressPackaging,
            progress.label
              ? replaceTemplate(t.exportProgressPackagingDetailFile, { file: progress.label })
              : t.exportProgressPackagingDetail,
            {
              stageProgress: progress.total > 0 ? progress.completed / progress.total : 1,
              indeterminate: false,
            },
          );
          break;
      }
    },
  });

  if (!options.skipDownload) {
    downloadBlob(result.blob, `${projectName}.usp`);
  }
  if (isPersistenceSnapshotCurrent()) {
    markAllSaved();
  }

  return {
    partial: result.partial,
    blob: result.blob,
    warnings: result.warnings.map((warning) => warning.message),
    issues: result.warnings.map((warning) => ({
      code: warning.code,
      message: warning.message,
      context: warning.context,
    })),
  };
}

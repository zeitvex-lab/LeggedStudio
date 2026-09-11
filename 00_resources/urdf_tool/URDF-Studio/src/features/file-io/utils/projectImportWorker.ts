import type { Language } from '@/shared/i18n';

import type { ImportedProjectArchiveData } from './projectImport.ts';

export interface ImportProjectWorkerRequest {
  type: 'import-project';
  requestId: number;
  file: Blob;
  lang?: Language;
}

export interface ImportProjectResultWorkerResponse {
  type: 'import-project-result';
  requestId: number;
  result: ImportedProjectArchiveData;
}

export interface ImportProjectErrorWorkerResponse {
  type: 'import-project-error';
  requestId: number;
  error: string;
}

export type ProjectImportWorkerRequest = ImportProjectWorkerRequest;

export type ProjectImportWorkerResponse =
  | ImportProjectResultWorkerResponse
  | ImportProjectErrorWorkerResponse;

import type {
  ProjectArchiveWorkerPayload,
  ProjectArchiveWorkerResultPayload,
} from './projectArchiveWorkerTransfer.ts';

export interface BuildProjectArchiveWorkerRequest {
  type: 'build-project-archive';
  requestId: number;
  payload: ProjectArchiveWorkerPayload;
  compressionLevel?: number;
}

export interface BuildProjectArchiveProgressWorkerResponse {
  type: 'build-project-archive-progress';
  requestId: number;
  completed: number;
  total: number;
  label?: string;
}

export interface BuildProjectArchiveResultWorkerResponse {
  type: 'build-project-archive-result';
  requestId: number;
  result: ProjectArchiveWorkerResultPayload;
}

export interface BuildProjectArchiveErrorWorkerResponse {
  type: 'build-project-archive-error';
  requestId: number;
  error: string;
}

export type ProjectArchiveWorkerRequest = BuildProjectArchiveWorkerRequest;

export type ProjectArchiveWorkerResponse =
  | BuildProjectArchiveProgressWorkerResponse
  | BuildProjectArchiveResultWorkerResponse
  | BuildProjectArchiveErrorWorkerResponse;

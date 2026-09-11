import type { SourceCodeDocumentFlavor, XmlCompletionEntry } from '../types';
import type { ValidationError } from './urdfValidation.ts';
import type { XmlDocumentValidationTexts } from './xmlDocumentValidation.ts';

export interface XmlCompletionWorkerRequest {
  type: 'xml-completion';
  requestId: number;
  documentFlavor: SourceCodeDocumentFlavor;
  textBeforeCursor: string;
}

export interface XmlValidationWorkerRequest {
  type: 'xml-validation';
  requestId: number;
  documentFlavor: SourceCodeDocumentFlavor;
  code: string;
  texts: XmlDocumentValidationTexts;
}

export type XmlEditorWorkerRequest =
  | XmlCompletionWorkerRequest
  | XmlValidationWorkerRequest;

export interface XmlCompletionWorkerResult {
  type: 'xml-completion-result';
  requestId: number;
  entries: XmlCompletionEntry[];
}

export interface XmlValidationWorkerResult {
  type: 'xml-validation-result';
  requestId: number;
  errors: ValidationError[];
}

export interface XmlWorkerErrorResult {
  type: 'xml-worker-error';
  requestId: number;
  error: string;
}

export type XmlEditorWorkerResponse =
  | XmlCompletionWorkerResult
  | XmlValidationWorkerResult
  | XmlWorkerErrorResult;

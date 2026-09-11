/**
 * Code Editor Feature Module
 * Provides URDF/XML code editing and viewing capabilities
 */

// Components
export { SourceCodeEditor } from './components/SourceCodeEditor';

// Types
export type { SourceCodeDocumentFlavor, SourceCodeEditorLanguageId } from './types';
export type {
  SourceCodeEditorDocument,
  SourceCodeEditorProps,
} from './components/SourceCodeEditor';
export type {
  SourceCodeDirtyRange,
  SourceCodeEditorApplyRequest,
} from './utils/sourceCodeEditorSession';

// App-facing runtime helpers
export { preloadMonacoEditor, preloadMonacoEditorWorker } from './utils/monacoLoader';

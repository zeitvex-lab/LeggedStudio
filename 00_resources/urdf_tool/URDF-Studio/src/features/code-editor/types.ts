export type SourceCodeDocumentFlavor = 'urdf' | 'mjcf' | 'usd' | 'equivalent-mjcf' | 'xacro' | 'sdf';

export type SourceCodeEditorLanguageId = 'urdf' | 'xacro' | 'xml' | 'plaintext';

export type XmlCompletionEntryKind = 'tag' | 'attribute' | 'value' | 'snippet';

export interface XmlCompletionEntry {
  label: string;
  kind: XmlCompletionEntryKind;
  insertText: string;
  documentation?: string;
  insertAsSnippet?: boolean;
}

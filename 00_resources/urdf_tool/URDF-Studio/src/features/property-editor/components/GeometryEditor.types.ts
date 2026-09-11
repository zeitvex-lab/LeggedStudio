import type { Language } from '@/store/uiStore';
import type { RobotState, UrdfLink, UrdfVisual } from '@/types';
import { GeometryType } from '@/types';
import type { translations } from '@/shared/i18n';

export type GeometryEditorTranslations = (typeof translations)['en'];
export type GeometryEditorCategory = 'visual' | 'collision';
export type GeometryUpdate = Partial<UrdfVisual>;

export interface GeometryEditorProps {
  componentId: string;
  data: UrdfLink;
  robot: RobotState;
  category: GeometryEditorCategory;
  onUpdate: (d: UrdfLink) => void;
  assets: Record<string, string>;
  onUploadAsset: (file: File) => void;
  onDeleteAsset?: (path: string) => void;
  t: GeometryEditorTranslations;
  lang: Language;
  isTabbed?: boolean;
  showCollisionDeleteAction?: boolean;
  sourceFilePath?: string;
  onLinkNameChange?: (name: string) => void;
}

export interface DimensionInputField {
  label: string;
  max?: number;
  min?: number;
  onChange: (value: number) => void;
  value: number;
}

export interface GeometrySnapshot {
  dimensions?: UrdfVisual['dimensions'];
  origin?: UrdfVisual['origin'];
  meshPath?: string;
  assetRef?: string;
  mjcfHfield?: UrdfVisual['mjcfHfield'];
  color?: string;
}

export type GeometrySnapshotCache = Record<
  string,
  Partial<Record<GeometryType, GeometrySnapshot>>
>;

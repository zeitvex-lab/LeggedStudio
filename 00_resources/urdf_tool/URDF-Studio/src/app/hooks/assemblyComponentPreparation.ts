import type { RobotFile } from '@/types';

import type { ImportPreparationOverlayState } from './useFileImport';

interface AssemblyComponentPreparationTranslations {
  addingAssemblyComponentToWorkspace: string;
  groundingAssemblyComponent: string;
  loadingRobot: string;
  preparingAssemblyComponent: string;
}

type AssemblyComponentPreparationStage = 'prepare' | 'add' | 'ground';

export function buildAssemblyComponentPreparationOverlayState(
  file: RobotFile,
  stage: AssemblyComponentPreparationStage,
  t: AssemblyComponentPreparationTranslations,
): ImportPreparationOverlayState {
  const fileLabel = file.name.split('/').pop() ?? file.name;

  if (stage === 'ground') {
    return {
      label: t.loadingRobot,
      detail: fileLabel,
      progress: 0.92,
      statusLabel: '3/3',
      stageLabel: t.groundingAssemblyComponent,
    };
  }

  if (stage === 'add') {
    return {
      label: t.loadingRobot,
      detail: fileLabel,
      progress: 0.72,
      statusLabel: '2/3',
      stageLabel: t.addingAssemblyComponentToWorkspace,
    };
  }

  return {
    label: t.loadingRobot,
    detail: fileLabel,
    progress: 0.36,
    statusLabel: '1/3',
    stageLabel: t.preparingAssemblyComponent,
  };
}

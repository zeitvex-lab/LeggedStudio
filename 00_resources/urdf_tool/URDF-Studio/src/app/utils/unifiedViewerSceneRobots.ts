import type { RobotData } from '@/types';

// `robot` is the editor-side robot (may carry a `selection` field when a
// RobotState is passed in); `viewerRobot` is the selection-free RobotData
// fed to the canvas. When the assembly workspace is active, the closed-loop
// solver wants the merged viewer scene; otherwise it wants the source robot.
// The downstream consumer (closedLoopRobotState) only reads
// links/joints/closedLoopConstraints, all on RobotData — so accepting either
// shape under RobotData is safe.
export function resolveUnifiedViewerEditorRobot({
  robot,
  viewerRobot,
  assemblyWorkspaceActive,
}: {
  robot: RobotData;
  viewerRobot: RobotData;
  assemblyWorkspaceActive: boolean;
}): RobotData {
  return assemblyWorkspaceActive ? viewerRobot : robot;
}

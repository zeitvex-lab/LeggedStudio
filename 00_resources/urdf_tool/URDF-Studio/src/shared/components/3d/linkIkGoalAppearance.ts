export const LINK_IK_GOAL_NAME = '__ik_goal__';
export const LINK_IK_GOAL_RENDER_ORDER = 9_990;

export interface LinkIkGoalPalette {
  halo: string;
  haloOpacity: number;
  shell: string;
  shellOpacity: number;
  core: string;
  coreOpacity: number;
  ring: string;
  ringOpacity: number;
}

export interface LinkIkGoalScales {
  haloRadius: number;
  shellRadius: number;
  coreRadius: number;
  ringRadius: number;
  ringTubeRadius: number;
}

export function resolveLinkIkGoalPalette(theme: 'light' | 'dark'): LinkIkGoalPalette {
  if (theme === 'light') {
    return {
      halo: '#7cc4ff',
      haloOpacity: 0.16,
      shell: '#007AFF',
      shellOpacity: 0.24,
      core: '#f8fbff',
      coreOpacity: 0.96,
      ring: '#007AFF',
      ringOpacity: 0.92,
    };
  }

  return {
    halo: '#38bdf8',
    haloOpacity: 0.18,
    shell: '#0ea5e9',
    shellOpacity: 0.28,
    core: '#e0f2fe',
    coreOpacity: 0.9,
    ring: '#7dd3fc',
    ringOpacity: 0.94,
  };
}

export function resolveLinkIkGoalScales(radius: number): LinkIkGoalScales {
  return {
    haloRadius: radius * 1.5,
    shellRadius: radius * 1.12,
    coreRadius: radius * 0.76,
    ringRadius: radius * 1.82,
    ringTubeRadius: Math.max(radius * 0.12, 0.0035),
  };
}

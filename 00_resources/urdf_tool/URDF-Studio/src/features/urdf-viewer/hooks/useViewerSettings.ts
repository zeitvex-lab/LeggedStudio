import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { useUIStore } from '@/store';
import {
  DEFAULT_ORIGIN_AXES_SIZE,
  normalizeOriginAxesSize,
} from '@/shared/components/3d/helpers/coordinateAxesSizing';
import { isIkDragToolEnabled } from '@/shared/utils/ikDragFeatureGate';
import type { ViewerInteractiveLayer } from '../types';
import { resolveInteractiveLayerPriority } from '../utils/interactiveLayerPriority';

const ACTIVE_OVERLAY_LAYER_STORAGE_KEY = 'urdf_viewer_active_overlay_layer_v1';
const ORIGIN_OVERLAY_STORAGE_KEY = 'urdf_viewer_origin_overlay_v2';
const COLLISION_ALWAYS_ON_TOP_STORAGE_KEY = 'urdf_viewer_collision_always_on_top';
const IK_HANDLE_ALWAYS_ON_TOP_STORAGE_KEY = 'urdf_viewer_ik_handle_always_on_top';
const CENTER_OF_MASS_OVERLAY_STORAGE_KEY = 'urdf_viewer_com_overlay';
const INERTIA_OVERLAY_STORAGE_KEY = 'urdf_viewer_inertia_overlay';
const JOINT_AXIS_OVERLAY_STORAGE_KEY = 'urdf_viewer_joint_axis_overlay';
const SHOW_COLLISION_STORAGE_KEY = 'urdf_viewer_show_collision';
const SHOW_VISUAL_STORAGE_KEY = 'urdf_viewer_show_visual';
const SHOW_CENTER_OF_MASS_STORAGE_KEY = 'urdf_viewer_show_center_of_mass';
const SHOW_INERTIA_STORAGE_KEY = 'urdf_viewer_show_inertia';
const SHOW_ORIGINS_STORAGE_KEY = 'urdf_viewer_show_origins';
const SHOW_JOINT_AXES_STORAGE_KEY = 'urdf_viewer_show_joint_axes';
const SHOW_MJCF_SITES_STORAGE_KEY = 'urdf_viewer_show_mjcf_sites';

const OVERLAY_LAYER_PRIORITY: readonly ViewerOverlayLayer[] = [
  'collision',
  'origin-axes',
  'joint-axis',
  'center-of-mass',
  'inertia',
];

type ViewerOverlayLayer = Exclude<ViewerInteractiveLayer, 'visual' | 'ik-handle'>;

function isViewerOverlayLayer(value: unknown): value is ViewerOverlayLayer {
  return typeof value === 'string' && OVERLAY_LAYER_PRIORITY.includes(value as ViewerOverlayLayer);
}

function readStoredBoolean(key: string): boolean | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const saved = localStorage.getItem(key);
  if (saved === 'true') return true;
  if (saved === 'false') return false;
  return null;
}

function resolveInitialActiveOverlayLayer(): ViewerOverlayLayer | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const savedActiveOverlayLayer = localStorage.getItem(ACTIVE_OVERLAY_LAYER_STORAGE_KEY);
  if (savedActiveOverlayLayer === 'none') {
    return null;
  }
  if (isViewerOverlayLayer(savedActiveOverlayLayer)) {
    return savedActiveOverlayLayer;
  }

  const explicitLegacyOverlayState: Record<ViewerOverlayLayer, boolean | null> = {
    collision: readStoredBoolean(COLLISION_ALWAYS_ON_TOP_STORAGE_KEY),
    'origin-axes': readStoredBoolean(ORIGIN_OVERLAY_STORAGE_KEY),
    'joint-axis': readStoredBoolean(JOINT_AXIS_OVERLAY_STORAGE_KEY),
    'center-of-mass': readStoredBoolean(CENTER_OF_MASS_OVERLAY_STORAGE_KEY),
    inertia: readStoredBoolean(INERTIA_OVERLAY_STORAGE_KEY),
  };

  const explicitEnabledLayer = OVERLAY_LAYER_PRIORITY.find(
    (layer) => explicitLegacyOverlayState[layer] === true,
  );
  if (explicitEnabledLayer) {
    return explicitEnabledLayer;
  }

  if (explicitLegacyOverlayState.collision === false) {
    return null;
  }

  return null;
}

export interface ViewerSettings {
  showCollision: boolean;
  setShowCollision: React.Dispatch<React.SetStateAction<boolean>>;
  showCollisionAlwaysOnTop: boolean;
  setShowCollisionAlwaysOnTop: React.Dispatch<React.SetStateAction<boolean>>;
  localShowVisual: boolean;
  setLocalShowVisual: React.Dispatch<React.SetStateAction<boolean>>;
  showIkHandles: boolean;
  setShowIkHandles: React.Dispatch<React.SetStateAction<boolean>>;
  showIkHandlesAlwaysOnTop: boolean;
  setShowIkHandlesAlwaysOnTop: React.Dispatch<React.SetStateAction<boolean>>;
  showCenterOfMass: boolean;
  setShowCenterOfMass: React.Dispatch<React.SetStateAction<boolean>>;
  showCoMOverlay: boolean;
  setShowCoMOverlay: React.Dispatch<React.SetStateAction<boolean>>;
  centerOfMassSize: number;
  setCenterOfMassSize: React.Dispatch<React.SetStateAction<number>>;
  showInertia: boolean;
  setShowInertia: React.Dispatch<React.SetStateAction<boolean>>;
  showInertiaOverlay: boolean;
  setShowInertiaOverlay: React.Dispatch<React.SetStateAction<boolean>>;
  showOrigins: boolean;
  setShowOrigins: React.Dispatch<React.SetStateAction<boolean>>;
  showOriginsOverlay: boolean;
  setShowOriginsOverlay: React.Dispatch<React.SetStateAction<boolean>>;
  originSize: number;
  setOriginSize: React.Dispatch<React.SetStateAction<number>>;
  showMjcfSites: boolean;
  setShowMjcfSites: React.Dispatch<React.SetStateAction<boolean>>;
  showJointAxes: boolean;
  setShowJointAxes: React.Dispatch<React.SetStateAction<boolean>>;
  showJointAxesOverlay: boolean;
  setShowJointAxesOverlay: React.Dispatch<React.SetStateAction<boolean>>;
  jointAxisSize: number;
  setJointAxisSize: React.Dispatch<React.SetStateAction<number>>;
  interactionLayerPriority: ViewerInteractiveLayer[];
  recordInteractionLayerActivation: (layer: ViewerInteractiveLayer) => void;
  modelOpacity: number;
  setModelOpacity: React.Dispatch<React.SetStateAction<number>>;
  highlightMode: 'link' | 'collision';
  setHighlightMode: React.Dispatch<React.SetStateAction<'link' | 'collision'>>;
  isOptionsCollapsed: boolean;
  toggleOptionsCollapsed: () => void;
  isJointsCollapsed: boolean;
  toggleJointsCollapsed: () => void;
}

export function useViewerSettings(): ViewerSettings {
  const viewOptions = useUIStore((state) => state.viewOptions);
  const setViewOption = useUIStore((state) => state.setViewOption);

  const {
    showCollision,
    showIkHandles,
    showJointAxes,
    showInertia,
    showCenterOfMass,
    modelOpacity,
  } = viewOptions;
  const effectiveShowIkHandles = isIkDragToolEnabled() && showIkHandles;

  const [activeOverlayLayer, setActiveOverlayLayerState] = useState<ViewerOverlayLayer | null>(() =>
    resolveInitialActiveOverlayLayer(),
  );

  const [localShowVisualState, setLocalShowVisualState] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(SHOW_VISUAL_STORAGE_KEY);
      return saved !== 'false';
    }
    return true;
  });
  const [showIkHandlesAlwaysOnTop, setShowIkHandlesAlwaysOnTopState] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(IK_HANDLE_ALWAYS_ON_TOP_STORAGE_KEY);
      return saved !== 'false';
    }
    return true;
  });

  const [centerOfMassSize, setCenterOfMassSize] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('urdf_viewer_com_size');
      return saved ? Math.min(parseFloat(saved), 0.5) : 0.01;
    }
    return 0.01;
  });

  const [showOriginsState, setShowOriginsState] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(SHOW_ORIGINS_STORAGE_KEY) === 'true';
    }
    return false;
  });
  const [showMjcfSitesState, setShowMjcfSitesState] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(SHOW_MJCF_SITES_STORAGE_KEY) === 'true';
    }
    return false;
  });

  const [originSize, setOriginSizeState] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('urdf_viewer_origin_size');
      return saved ? normalizeOriginAxesSize(saved) : DEFAULT_ORIGIN_AXES_SIZE;
    }
    return DEFAULT_ORIGIN_AXES_SIZE;
  });
  const setOriginSize: Dispatch<SetStateAction<number>> = useCallback((nextValue) => {
    setOriginSizeState((currentValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(currentValue) : nextValue;
      return normalizeOriginAxesSize(resolvedValue, currentValue);
    });
  }, []);

  const [jointAxisSize, setJointAxisSize] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('urdf_viewer_joint_axis_size');
      return saved ? Math.min(parseFloat(saved), 2.0) : 0.5;
    }
    return 0.5;
  });

  const [highlightMode, setHighlightMode] = useState<'link' | 'collision'>('link');
  const [interactionActivationOrder, setInteractionActivationOrder] = useState<
    Record<ViewerInteractiveLayer, number>
  >({
    'ik-handle': 0,
    visual: 1,
    collision: 0,
    'origin-axes': 0,
    'joint-axis': 0,
    'center-of-mass': 0,
    inertia: 0,
  });

  const [isOptionsCollapsed, setIsOptionsCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('urdf_viewer_options_collapsed');
      return saved === 'true';
    }
    return false;
  });
  const [isJointsCollapsed, setIsJointsCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('urdf_viewer_joints_collapsed');
      return saved === 'true';
    }
    return false;
  });

  const showCollisionAlwaysOnTop = activeOverlayLayer === 'collision';
  const showOriginsOverlay = activeOverlayLayer === 'origin-axes';
  const showJointAxesOverlay = activeOverlayLayer === 'joint-axis';
  const showCoMOverlay = activeOverlayLayer === 'center-of-mass';
  const showInertiaOverlay = activeOverlayLayer === 'inertia';

  useEffect(() => {
    localStorage.setItem(SHOW_VISUAL_STORAGE_KEY, localShowVisualState.toString());
  }, [localShowVisualState]);

  useEffect(() => {
    localStorage.setItem('urdf_viewer_origin_size', originSize.toString());
  }, [originSize]);

  useEffect(() => {
    localStorage.setItem('urdf_viewer_com_size', centerOfMassSize.toString());
  }, [centerOfMassSize]);

  useEffect(() => {
    localStorage.setItem(SHOW_ORIGINS_STORAGE_KEY, showOriginsState.toString());
  }, [showOriginsState]);

  useEffect(() => {
    localStorage.setItem(SHOW_MJCF_SITES_STORAGE_KEY, showMjcfSitesState.toString());
  }, [showMjcfSitesState]);

  useEffect(() => {
    localStorage.setItem('urdf_viewer_joint_axis_size', jointAxisSize.toString());
  }, [jointAxisSize]);

  useEffect(() => {
    localStorage.setItem(IK_HANDLE_ALWAYS_ON_TOP_STORAGE_KEY, showIkHandlesAlwaysOnTop.toString());
  }, [showIkHandlesAlwaysOnTop]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_OVERLAY_LAYER_STORAGE_KEY, activeOverlayLayer ?? 'none');
    localStorage.setItem(COLLISION_ALWAYS_ON_TOP_STORAGE_KEY, showCollisionAlwaysOnTop.toString());
    localStorage.setItem(ORIGIN_OVERLAY_STORAGE_KEY, showOriginsOverlay.toString());
    localStorage.setItem(JOINT_AXIS_OVERLAY_STORAGE_KEY, showJointAxesOverlay.toString());
    localStorage.setItem(CENTER_OF_MASS_OVERLAY_STORAGE_KEY, showCoMOverlay.toString());
    localStorage.setItem(INERTIA_OVERLAY_STORAGE_KEY, showInertiaOverlay.toString());
  }, [
    activeOverlayLayer,
    showCoMOverlay,
    showCollisionAlwaysOnTop,
    showInertiaOverlay,
    showJointAxesOverlay,
    showOriginsOverlay,
  ]);

  const bumpInteractionLayer = useCallback((layer: ViewerInteractiveLayer) => {
    setInteractionActivationOrder((previous) => {
      const nextOrder = Math.max(...Object.values(previous)) + 1;
      if (previous[layer] === nextOrder) {
        return previous;
      }

      return {
        ...previous,
        [layer]: nextOrder,
      };
    });
  }, []);

  const setActiveOverlayLayer = useCallback(
    (layer: ViewerOverlayLayer | null) => {
      setActiveOverlayLayerState((previous) => {
        if (previous === layer) {
          return previous;
        }
        return layer;
      });
      if (layer) {
        bumpInteractionLayer(layer);
      }
    },
    [bumpInteractionLayer],
  );

  const localShowVisual = localShowVisualState;
  const showOrigins = showOriginsState;
  const showMjcfSites = showMjcfSitesState;

  const setShowCollision: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue = typeof nextValue === 'function' ? nextValue(showCollision) : nextValue;
      setViewOption('showCollision', resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('collision');
        if (!showCollisionAlwaysOnTop && activeOverlayLayer === null) {
          setActiveOverlayLayerState('collision');
        }
      } else if (showCollisionAlwaysOnTop) {
        setActiveOverlayLayer(null);
      }
    },
    [
      activeOverlayLayer,
      bumpInteractionLayer,
      setActiveOverlayLayer,
      setViewOption,
      showCollision,
      showCollisionAlwaysOnTop,
    ],
  );

  const setLocalShowVisual: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(localShowVisualState) : nextValue;
      setLocalShowVisualState(resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('visual');
      }
    },
    [bumpInteractionLayer, localShowVisualState],
  );

  const setShowCenterOfMass: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showCenterOfMass) : nextValue;
      setViewOption('showCenterOfMass', resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('center-of-mass');
      } else if (showCoMOverlay) {
        setActiveOverlayLayer(null);
      }
    },
    [bumpInteractionLayer, setActiveOverlayLayer, setViewOption, showCenterOfMass, showCoMOverlay],
  );

  const setShowInertia: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue = typeof nextValue === 'function' ? nextValue(showInertia) : nextValue;
      setViewOption('showInertia', resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('inertia');
      } else if (showInertiaOverlay) {
        setActiveOverlayLayer(null);
      }
    },
    [bumpInteractionLayer, setActiveOverlayLayer, setViewOption, showInertia, showInertiaOverlay],
  );

  const setShowOrigins: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showOriginsState) : nextValue;
      setShowOriginsState(resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('origin-axes');
      } else if (showOriginsOverlay) {
        setActiveOverlayLayer(null);
      }
    },
    [bumpInteractionLayer, setActiveOverlayLayer, showOriginsOverlay, showOriginsState],
  );

  const setShowMjcfSites: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showMjcfSitesState) : nextValue;
      setShowMjcfSitesState(resolvedValue);
    },
    [showMjcfSitesState],
  );

  const setShowJointAxes: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue = typeof nextValue === 'function' ? nextValue(showJointAxes) : nextValue;
      setViewOption('showJointAxes', resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('joint-axis');
      } else if (showJointAxesOverlay) {
        setActiveOverlayLayer(null);
      }
    },
    [
      bumpInteractionLayer,
      setActiveOverlayLayer,
      setViewOption,
      showJointAxes,
      showJointAxesOverlay,
    ],
  );

  const setShowIkHandles: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue = typeof nextValue === 'function' ? nextValue(showIkHandles) : nextValue;
      setViewOption('showIkHandles', resolvedValue);
      if (resolvedValue) {
        bumpInteractionLayer('ik-handle');
      }
    },
    [bumpInteractionLayer, setViewOption, showIkHandles],
  );

  const setShowIkHandlesAlwaysOnTop: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showIkHandlesAlwaysOnTop) : nextValue;
      setShowIkHandlesAlwaysOnTopState(resolvedValue);
      if (resolvedValue && showIkHandles) {
        bumpInteractionLayer('ik-handle');
      }
    },
    [bumpInteractionLayer, showIkHandles, showIkHandlesAlwaysOnTop],
  );

  const setShowCollisionAlwaysOnTopTracked: React.Dispatch<React.SetStateAction<boolean>> =
    useCallback(
      (nextValue) => {
        const resolvedValue =
          typeof nextValue === 'function' ? nextValue(showCollisionAlwaysOnTop) : nextValue;
        setActiveOverlayLayer(resolvedValue ? 'collision' : null);
      },
      [setActiveOverlayLayer, showCollisionAlwaysOnTop],
    );

  const setShowCoMOverlayTracked: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue = typeof nextValue === 'function' ? nextValue(showCoMOverlay) : nextValue;
      setActiveOverlayLayer(resolvedValue ? 'center-of-mass' : null);
    },
    [setActiveOverlayLayer, showCoMOverlay],
  );

  const setShowInertiaOverlayTracked: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showInertiaOverlay) : nextValue;
      setActiveOverlayLayer(resolvedValue ? 'inertia' : null);
    },
    [setActiveOverlayLayer, showInertiaOverlay],
  );

  const setShowOriginsOverlayTracked: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showOriginsOverlay) : nextValue;
      setActiveOverlayLayer(resolvedValue ? 'origin-axes' : null);
    },
    [setActiveOverlayLayer, showOriginsOverlay],
  );

  const setShowJointAxesOverlayTracked: React.Dispatch<React.SetStateAction<boolean>> = useCallback(
    (nextValue) => {
      const resolvedValue =
        typeof nextValue === 'function' ? nextValue(showJointAxesOverlay) : nextValue;
      setActiveOverlayLayer(resolvedValue ? 'joint-axis' : null);
    },
    [setActiveOverlayLayer, showJointAxesOverlay],
  );

  const interactionLayerPriority = useMemo(
    () =>
      resolveInteractiveLayerPriority({
        showVisual: localShowVisual,
        showIkHandles: effectiveShowIkHandles,
        showIkHandlesAlwaysOnTop,
        showCollision,
        showCollisionAlwaysOnTop,
        showOrigins,
        showOriginsOverlay,
        showJointAxes,
        showJointAxesOverlay,
        showCenterOfMass,
        showCoMOverlay,
        showInertia,
        showInertiaOverlay,
        activationOrder: interactionActivationOrder,
      }),
    [
      interactionActivationOrder,
      effectiveShowIkHandles,
      localShowVisual,
      showIkHandlesAlwaysOnTop,
      showCenterOfMass,
      showCoMOverlay,
      showCollision,
      showCollisionAlwaysOnTop,
      showInertia,
      showInertiaOverlay,
      showJointAxes,
      showJointAxesOverlay,
      showOrigins,
      showOriginsOverlay,
    ],
  );

  const setModelOpacity: React.Dispatch<React.SetStateAction<number>> = (nextValue) => {
    const resolvedValue = typeof nextValue === 'function' ? nextValue(modelOpacity) : nextValue;
    const clampedValue = Number.isFinite(resolvedValue)
      ? Math.max(0.1, Math.min(1, resolvedValue))
      : 1;
    setViewOption('modelOpacity', clampedValue);
  };

  const toggleOptionsCollapsed = () => {
    setIsOptionsCollapsed((prev) => {
      const newState = !prev;
      localStorage.setItem('urdf_viewer_options_collapsed', String(newState));
      return newState;
    });
  };

  const toggleJointsCollapsed = () => {
    setIsJointsCollapsed((prev) => {
      const newState = !prev;
      localStorage.setItem('urdf_viewer_joints_collapsed', String(newState));
      return newState;
    });
  };

  return {
    showCollision,
    setShowCollision,
    showCollisionAlwaysOnTop,
    setShowCollisionAlwaysOnTop: setShowCollisionAlwaysOnTopTracked,
    localShowVisual,
    setLocalShowVisual,
    showIkHandles: effectiveShowIkHandles,
    setShowIkHandles,
    showIkHandlesAlwaysOnTop,
    setShowIkHandlesAlwaysOnTop,
    showCenterOfMass,
    setShowCenterOfMass,
    showCoMOverlay,
    setShowCoMOverlay: setShowCoMOverlayTracked,
    centerOfMassSize,
    setCenterOfMassSize,
    showInertia,
    setShowInertia,
    showInertiaOverlay,
    setShowInertiaOverlay: setShowInertiaOverlayTracked,
    showOrigins,
    setShowOrigins,
    showOriginsOverlay,
    setShowOriginsOverlay: setShowOriginsOverlayTracked,
    originSize,
    setOriginSize,
    showMjcfSites,
    setShowMjcfSites,
    showJointAxes,
    setShowJointAxes,
    showJointAxesOverlay,
    setShowJointAxesOverlay: setShowJointAxesOverlayTracked,
    jointAxisSize,
    setJointAxisSize,
    interactionLayerPriority,
    recordInteractionLayerActivation: bumpInteractionLayer,
    modelOpacity,
    setModelOpacity,
    highlightMode,
    setHighlightMode,
    isOptionsCollapsed,
    toggleOptionsCollapsed,
    isJointsCollapsed,
    toggleJointsCollapsed,
  };
}

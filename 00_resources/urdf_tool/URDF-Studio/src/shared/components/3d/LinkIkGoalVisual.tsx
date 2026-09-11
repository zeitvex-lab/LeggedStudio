import React, { forwardRef, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

import { useEffectiveTheme } from '@/shared/hooks/useEffectiveTheme';

import {
  LINK_IK_GOAL_NAME,
  LINK_IK_GOAL_RENDER_ORDER,
  resolveLinkIkGoalPalette,
  resolveLinkIkGoalScales,
} from './linkIkGoalAppearance';

interface LinkIkGoalVisualProps {
  radius: number;
}

export const LinkIkGoalVisual = forwardRef<THREE.Group, LinkIkGoalVisualProps>(
  function LinkIkGoalVisual({ radius }, ref) {
    const effectiveTheme = useEffectiveTheme();
    const palette = useMemo(() => resolveLinkIkGoalPalette(effectiveTheme), [effectiveTheme]);
    const scales = useMemo(() => resolveLinkIkGoalScales(radius), [radius]);
    const haloRef = useRef<THREE.Mesh>(null);
    const ringRef = useRef<THREE.Mesh>(null);
    const haloMaterialRef = useRef<THREE.MeshBasicMaterial>(null);
    const ringMaterialRef = useRef<THREE.MeshBasicMaterial>(null);

    useFrame((state) => {
      const pulse = 1 + Math.sin(state.clock.elapsedTime * 2.4) * 0.035;
      if (haloRef.current) {
        haloRef.current.scale.setScalar(pulse);
      }
      if (ringRef.current) {
        ringRef.current.scale.setScalar(1 + (pulse - 1) * 0.8);
      }
      if (haloMaterialRef.current) {
        haloMaterialRef.current.opacity = palette.haloOpacity * (0.92 + (pulse - 1) * 2.2);
      }
      if (ringMaterialRef.current) {
        ringMaterialRef.current.opacity = palette.ringOpacity * (0.97 + (pulse - 1) * 1.4);
      }
    });

    return (
      <group ref={ref} name={LINK_IK_GOAL_NAME} userData={{ isHelper: true }}>
        <mesh ref={haloRef} renderOrder={LINK_IK_GOAL_RENDER_ORDER}>
          <sphereGeometry args={[scales.haloRadius, 24, 24]} />
          <meshBasicMaterial
            ref={haloMaterialRef}
            color={palette.halo}
            transparent
            opacity={palette.haloOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </mesh>
        <mesh renderOrder={LINK_IK_GOAL_RENDER_ORDER + 1}>
          <sphereGeometry args={[scales.shellRadius, 24, 24]} />
          <meshBasicMaterial
            color={palette.shell}
            transparent
            opacity={palette.shellOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </mesh>
        <mesh renderOrder={LINK_IK_GOAL_RENDER_ORDER + 2}>
          <sphereGeometry args={[scales.coreRadius, 24, 24]} />
          <meshBasicMaterial
            color={palette.core}
            transparent
            opacity={palette.coreOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </mesh>
        <mesh
          ref={ringRef}
          rotation={[Math.PI / 2, 0, 0]}
          renderOrder={LINK_IK_GOAL_RENDER_ORDER + 3}
        >
          <torusGeometry args={[scales.ringRadius, scales.ringTubeRadius, 12, 64]} />
          <meshBasicMaterial
            ref={ringMaterialRef}
            color={palette.ring}
            transparent
            opacity={palette.ringOpacity}
            depthTest={false}
            depthWrite={false}
          />
        </mesh>
      </group>
    );
  },
);

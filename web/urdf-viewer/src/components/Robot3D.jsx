/**
 * Robot 3D 组件
 * 渲染 URDF 解析后的机器人模型
 */

import { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid, Box, Sphere, Cylinder } from '@react-three/drei';
import * as THREE from 'three';

/**
 * 单个 Link 渲染组件
 */
function RobotLink({ linkData }) {
  if (!linkData.visual) return null;

  const { visual } = linkData;
  const { origin = { xyz: [0, 0, 0], rpy: [0, 0, 0] } } = visual;
  const color = visual.color ?
    new THREE.Color(visual.color[0], visual.color[1], visual.color[2]) :
    new THREE.Color(0.7, 0.7, 0.7);

  // 位置和旋转
  const position = origin.xyz;
  const rotation = origin.rpy; // Roll-Pitch-Yaw

  // 根据几何类型渲染
  const renderGeometry = () => {
    switch (visual.type) {
      case 'box':
        return (
          <Box args={visual.size}>
            <meshStandardMaterial color={color} />
          </Box>
        );

      case 'sphere':
        return (
          <Sphere args={[visual.radius, 32, 32]}>
            <meshStandardMaterial color={color} />
          </Sphere>
        );

      case 'cylinder':
        return (
          <Cylinder args={[visual.radius, visual.radius, visual.length, 32]}>
            <meshStandardMaterial color={color} />
          </Cylinder>
        );

      case 'mesh':
        // Phase 0: 暂不加载 STL/DAE，显示占位盒子
        return (
          <Box args={[0.1, 0.1, 0.1]}>
            <meshStandardMaterial color={color} wireframe />
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <group position={position} rotation={rotation}>
      {renderGeometry()}
    </group>
  );
}

/**
 * 递归渲染机器人树
 */
function RobotTreeNode({ node }) {
  if (!node) return null;

  return (
    <group>
      <RobotLink linkData={node} />

      {node.children && node.children.map((child, index) => (
        <group
          key={index}
          position={child.joint.origin?.xyz || [0, 0, 0]}
          rotation={child.joint.origin?.rpy || [0, 0, 0]}
        >
          <RobotTreeNode node={child.link} />
        </group>
      ))}
    </group>
  );
}

/**
 * Robot 3D 主组件
 */
export function Robot3D({ urdfData, robotTree }) {
  const controlsRef = useRef();

  if (!urdfData || !robotTree) {
    return (
      <div style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#666'
      }}>
        <p>请上传 URDF 文件</p>
      </div>
    );
  }

  return (
    <Canvas
      camera={{ position: [3, 3, 3], fov: 50 }}
      style={{ background: '#0a0a0a' }}
    >
      {/* 光照 */}
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 5, 5]} intensity={1} />
      <directionalLight position={[-5, -5, -5]} intensity={0.3} />

      {/* 机器人模型 */}
      <RobotTreeNode node={robotTree} />

      {/* 网格辅助线 */}
      <Grid
        args={[10, 10]}
        cellColor="#444"
        sectionColor="#666"
        fadeDistance={20}
        fadeStrength={1}
      />

      {/* 控制器 */}
      <OrbitControls
        ref={controlsRef}
        enableDamping
        dampingFactor={0.05}
        minDistance={1}
        maxDistance={20}
      />
    </Canvas>
  );
}

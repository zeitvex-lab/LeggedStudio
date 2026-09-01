# Task 0.3：Three.js URDF 渲染原型

**目标**：验证 URDF 3D 预览可行性

**参考**：
- URDF Studio (`urdf_tool/URDF-Studio/src/core/`)
- 项目愿景第四章（步骤 1：模型验证）

---

## 📋 技术方案

### 技术栈

```
React + Three.js + React Three Fiber
├── URDF 解析：XML → 树结构
├── STL 加载：STLLoader
├── 渲染引擎：Three.js
└── 交互控制：OrbitControls
```

---

## 🎯 Phase 0 目标

**不做**：
- ❌ 完整 URDF 支持（碰撞体、惯量等）
- ❌ 关节动画
- ❌ 物理模拟
- ❌ 美化渲染

**只做**：
- ✅ 解析 URDF XML（链接、关节、mesh 路径）
- ✅ 加载 STL 文件
- ✅ 显示 3D 模型
- ✅ 鼠标旋转查看

---

## 📐 实现步骤

### Step 1：创建 React + Three.js 项目

```bash
cd legged_studio/web
npm create vite@latest urdf-viewer -- --template react
cd urdf-viewer
npm install three @react-three/fiber @react-three/drei
```

**文件结构**：
```
web/urdf-viewer/
├── src/
│   ├── components/
│   │   ├── URDFParser.js      # URDF XML 解析
│   │   ├── STLLoader.js        # STL 文件加载
│   │   ├── Robot3D.js          # 3D 模型渲染
│   │   └── Viewer.js           # 主视图
│   └── App.jsx
└── package.json
```

---

### Step 2：实现 URDF 解析器（简化版）

**参考**：URDF Studio 的 `urdf_tool/URDF-Studio/src/core/parsers/`

**最小实现**：
```javascript
// URDFParser.js
export function parseURDF(xmlString) {
  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlString, 'text/xml');
  
  const robot = {
    name: xml.querySelector('robot').getAttribute('name'),
    links: [],
    joints: []
  };

  // 解析 links
  xml.querySelectorAll('link').forEach(link => {
    const name = link.getAttribute('name');
    const visual = link.querySelector('visual geometry mesh');
    
    robot.links.push({
      name,
      meshPath: visual ? visual.getAttribute('filename') : null
    });
  });

  // 解析 joints（简化版，只记录父子关系）
  xml.querySelectorAll('joint').forEach(joint => {
    robot.joints.push({
      name: joint.getAttribute('name'),
      parent: joint.querySelector('parent').getAttribute('link'),
      child: joint.querySelector('child').getAttribute('link')
    });
  });

  return robot;
}
```

---

### Step 3：实现 STL 加载器

```javascript
// STLLoader.js
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';

export function loadSTL(path) {
  return new Promise((resolve, reject) => {
    const loader = new STLLoader();
    loader.load(
      path,
      (geometry) => resolve(geometry),
      undefined,
      (error) => reject(error)
    );
  });
}
```

---

### Step 4：渲染 3D 模型

```javascript
// Robot3D.jsx
import { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { loadSTL } from './STLLoader';

function RobotMesh({ meshPath }) {
  const [geometry, setGeometry] = useState(null);

  useEffect(() => {
    loadSTL(meshPath).then(setGeometry);
  }, [meshPath]);

  if (!geometry) return null;

  return (
    <mesh geometry={geometry}>
      <meshStandardMaterial color="#888888" />
    </mesh>
  );
}

export function Robot3D({ urdfData }) {
  return (
    <Canvas camera={{ position: [2, 2, 2] }}>
      <ambientLight intensity={0.5} />
      <directionalLight position={[5, 5, 5]} />
      
      {urdfData.links.map(link => (
        link.meshPath && <RobotMesh key={link.name} meshPath={link.meshPath} />
      ))}
      
      <OrbitControls />
      <gridHelper args={[10, 10]} />
    </Canvas>
  );
}
```

---

### Step 5：主视图

```javascript
// Viewer.jsx
import { useState } from 'react';
import { parseURDF } from './URDFParser';
import { Robot3D } from './Robot3D';

export function Viewer() {
  const [urdfData, setUrdfData] = useState(null);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    const reader = new FileReader();
    
    reader.onload = (event) => {
      const data = parseURDF(event.target.result);
      setUrdfData(data);
    };
    
    reader.readAsText(file);
  };

  return (
    <div style={{ width: '100vw', height: '100vh' }}>
      <input type="file" accept=".urdf" onChange={handleFileUpload} />
      
      {urdfData && (
        <div style={{ width: '100%', height: '90%' }}>
          <Robot3D urdfData={urdfData} />
        </div>
      )}
    </div>
  );
}
```

---

## 🧪 测试用例

### 测试 1：Go2 URDF

**文件**：查找 Go2 URDF（从 asset inventory）
```bash
# 搜索 Go2 URDF
find C:/Users/31560/Documents/00_open -name "*go2*.urdf" -type f
```

**预期**：
- ✅ 解析成功
- ✅ 显示 Go2 模型
- ✅ 可旋转查看
- ✅ 帧率 >30 FPS

---

### 测试 2：简单测试 URDF

**创建最小测试文件**：
```xml
<!-- test_simple.urdf -->
<robot name="test">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.5 0.5 0.5"/>
      </geometry>
    </visual>
  </link>
</robot>
```

**预期**：显示一个立方体

---

## ✅ 验收标准

### 功能验收
- [ ] 能上传并解析 URDF 文件
- [ ] 显示 3D 模型（至少支持 box/mesh）
- [ ] 鼠标可旋转、缩放
- [ ] 显示网格辅助线

### 性能验收
- [ ] 加载 Go2 模型 <3 秒
- [ ] 渲染帧率 >30 FPS
- [ ] 内存占用 <500 MB

### 代码验收
- [ ] 代码结构清晰
- [ ] 可扩展（后续添加关节、动画）
- [ ] 错误处理（URDF 解析失败）

---

## 📊 任务拆解

### Task 0.3.1：创建项目骨架
- **预计**：30 分钟
- **验收**：React + Three.js 项目可运行

### Task 0.3.2：实现 URDF 解析
- **预计**：1 小时
- **验收**：能解析简单 URDF

### Task 0.3.3：实现 STL 加载
- **预计**：1 小时
- **验收**：能加载并显示 STL

### Task 0.3.4：集成测试
- **预计**：1 小时
- **验收**：Go2 模型显示成功

---

## 🔗 参考资源

### URDF Studio 源码
```
urdf_tool/URDF-Studio/src/core/
├── parsers/
│   └── urdf-parser.js          # URDF 解析
├── loaders/
│   └── urdf-loader.js          # 资源加载
└── components/
    └── urdf-viewer.vue         # 3D 查看器
```

### URDF 规范
- 链接：http://wiki.ros.org/urdf/XML
- 支持元素：robot, link, joint, visual, collision

### Three.js 文档
- STLLoader：https://threejs.org/docs/#examples/en/loaders/STLLoader
- OrbitControls：https://threejs.org/docs/#examples/en/controls/OrbitControls

---

## 🎯 Phase 1 扩展（可选）

**如果 Phase 0 顺利，Phase 1 可添加**：
- 关节旋转控制
- 材质和纹理
- 碰撞体显示
- 导出截图

**Phase 0 不做这些**，只验证基本可行性。

---

**下一步**：创建 React + Three.js 项目

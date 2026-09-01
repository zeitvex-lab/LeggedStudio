# URDF Viewer

**Legged Studio - Three.js URDF 渲染器原型**

---

## 📋 功能

### Phase 0（当前）
- ✅ URDF XML 解析
- ✅ 基础几何体渲染（box/sphere/cylinder）
- ✅ 颜色材质支持
- ✅ 鼠标旋转/缩放查看
- ✅ 网格辅助线

### Phase 1（计划）
- 📋 STL/DAE 文件加载
- 📋 关节动画
- 📋 材质纹理
- 📋 碰撞体显示

---

## 🚀 快速开始

### 安装依赖
```bash
cd web/urdf-viewer
npm install
```

**依赖**：
- React 18
- Three.js 0.160
- @react-three/fiber
- @react-three/drei
- Vite

### 启动开发服务器
```bash
npm run dev
# 访问 http://localhost:3000
```

### 构建生产版本
```bash
npm run build
# 输出到 dist/
```

---

## 💻 使用方法

### 1. 加载示例
点击"加载示例"按钮，查看简单立方体

### 2. 上传 URDF
点击"上传 URDF"，选择 `.urdf` 或 `.xml` 文件

### 3. 操作
- **旋转**：鼠标左键拖拽
- **缩放**：鼠标滚轮
- **平移**：鼠标右键拖拽

---

## 📐 支持的几何体

### Phase 0 已支持
```xml
<!-- 立方体 -->
<geometry>
  <box size="0.5 0.5 0.5"/>
</geometry>

<!-- 球体 -->
<geometry>
  <sphere radius="0.5"/>
</geometry>

<!-- 圆柱 -->
<geometry>
  <cylinder radius="0.2" length="1.0"/>
</geometry>
```

### 颜色材质
```xml
<material name="blue">
  <color rgba="0.3 0.5 0.8 1.0"/>
</material>
```

### Phase 1 将支持
```xml
<!-- STL/DAE 文件 -->
<geometry>
  <mesh filename="package://robot/meshes/base_link.stl"/>
</geometry>
```

---

## 📂 文件结构

```
urdf-viewer/
├── src/
│   ├── App.jsx              # 主应用
│   ├── App.css              # 样式
│   ├── main.jsx             # 入口
│   ├── components/
│   │   └── Robot3D.jsx      # 3D 渲染组件
│   └── utils/
│       └── urdfParser.js    # URDF 解析器
├── index.html               # HTML 模板
├── package.json             # 依赖配置
└── vite.config.js           # Vite 配置
```

---

## 🧪 测试

### 示例 URDF（内置）
```xml
<robot name="simple_box">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.5 0.5 0.5"/>
      </geometry>
      <material name="blue">
        <color rgba="0.3 0.5 0.8 1.0"/>
      </material>
    </visual>
  </link>
</robot>
```

### 测试真实机器人
从 asset inventory 找 URDF：
```bash
# 搜索 Go2 URDF
find C:/Users/31560/Documents/00_open -name "*go2*.urdf"
```

---

## 🔧 开发

### 添加新几何类型
在 `Robot3D.jsx` 的 `renderGeometry()` 中添加：
```javascript
case 'new_type':
  return <NewGeometry />;
```

### 修改渲染器
`Robot3D.jsx` 使用 React Three Fiber，基于 Three.js

---

## 🎯 Phase 0 限制

- ❌ 不加载 STL/DAE（显示占位盒子）
- ❌ 无关节动画
- ❌ 无材质纹理
- ❌ 仅渲染 visual，不渲染 collision

**Phase 0 目标**：验证技术可行性

---

## 📖 参考

- URDF 规范：http://wiki.ros.org/urdf/XML
- Three.js：https://threejs.org/
- React Three Fiber：https://docs.pmnd.rs/react-three-fiber

---

**Task 0.3 原型完成！** ✨

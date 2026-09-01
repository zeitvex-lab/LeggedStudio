/**
 * URDF Viewer 主应用
 */

import { useState } from 'react';
import { Robot3D } from './components/Robot3D';
import { parseURDF, buildRobotTree } from './utils/urdfParser';
import './App.css';

function App() {
  const [urdfData, setUrdfData] = useState(null);
  const [robotTree, setRobotTree] = useState(null);
  const [error, setError] = useState(null);
  const [fileName, setFileName] = useState('');

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setFileName(file.name);
    setError(null);

    const reader = new FileReader();

    reader.onload = (event) => {
      try {
        const data = parseURDF(event.target.result);
        const tree = buildRobotTree(data);

        setUrdfData(data);
        setRobotTree(tree);

        console.log('URDF 解析成功:', data);
        console.log('机器人树:', tree);
      } catch (err) {
        setError('解析失败: ' + err.message);
        console.error('URDF 解析错误:', err);
      }
    };

    reader.onerror = () => {
      setError('文件读取失败');
    };

    reader.readAsText(file);
  };

  const handleLoadExample = () => {
    // 加载示例 URDF（简单立方体）
    const exampleURDF = `<?xml version="1.0"?>
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
</robot>`;

    try {
      const data = parseURDF(exampleURDF);
      const tree = buildRobotTree(data);

      setUrdfData(data);
      setRobotTree(tree);
      setFileName('示例: 简单立方体');
      setError(null);
    } catch (err) {
      setError('示例加载失败: ' + err.message);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>🤖 URDF Viewer</h1>
        <p>Legged Studio - Phase 0 原型</p>
      </header>

      <div className="controls">
        <input
          type="file"
          accept=".urdf,.xml"
          onChange={handleFileUpload}
          id="file-input"
          style={{ display: 'none' }}
        />

        <label htmlFor="file-input" className="button button-primary">
          📁 上传 URDF
        </label>

        <button onClick={handleLoadExample} className="button button-secondary">
          ✨ 加载示例
        </button>

        {fileName && (
          <span className="file-name">
            当前: {fileName}
          </span>
        )}
      </div>

      {error && (
        <div className="error">
          ❌ {error}
        </div>
      )}

      {urdfData && (
        <div className="info">
          <span>机器人: <strong>{urdfData.name}</strong></span>
          <span>Links: {urdfData.links.length}</span>
          <span>Joints: {urdfData.joints.length}</span>
        </div>
      )}

      <div className="viewer">
        <Robot3D urdfData={urdfData} robotTree={robotTree} />
      </div>

      <footer className="footer">
        <p>Phase 0 功能：基础几何体（box/sphere/cylinder）</p>
        <p>Phase 1 将支持：STL/DAE 加载、关节动画、材质纹理</p>
      </footer>
    </div>
  );
}

export default App;

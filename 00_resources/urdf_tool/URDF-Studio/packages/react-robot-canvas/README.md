# @urdf-studio/react-robot-canvas

Reusable React 3D robot canvas with `URDF` and `MJCF` import support.

## Install

```bash
npm install @urdf-studio/react-robot-canvas react react-dom three @react-three/fiber @react-three/drei
```

## Usage

```tsx
import { RobotCanvas } from '@urdf-studio/react-robot-canvas';
import '@urdf-studio/react-robot-canvas/style.css';

export function Demo() {
  return (
    <div style={{ width: '100%', height: 640 }}>
      <RobotCanvas
        source={{
          format: 'auto',
          content: robotXml,
          sourceFilePath: '/robots/demo.urdf',
        }}
        assets={assetMap}
        lang="en"
        theme="dark"
        display={{
          showVisual: true,
          showCollision: false,
        }}
      />
    </div>
  );
}
```

## Current API

- `source.format` supports `auto | urdf | mjcf`
- `selection`, `hoveredSelection`, `jointAngles` support controlled usage
- `display` supports visual/collision toggles, highlight mode, transform mode, and viewer overlays
- viewer overlays already include inertia, center of mass, origins, and joint axes
- `groundPlaneOffset` is prop-driven

## Current limitation

- `assets` is still a synchronous `Record<string, string>` map. A future version should expose `assetResolver`.
- This package is published as modern ESM. It is intended for Vite / modern bundler consumers.

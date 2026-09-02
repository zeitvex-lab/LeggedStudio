# URDF viewer component

This directory contains the optional React/Three.js viewer prototype. The
production entry point is the Web Workbench at `../workbench.html`; this
component is not a standalone desktop application.

## Development

```powershell
cd web/urdf-viewer
npm install
npm run dev
```

The component currently renders basic URDF geometry and camera controls. Mesh
loading, articulated playback, collision overlays, and richer native MJLab
visualization remain separate adapter work and must not be reported as
completed capabilities.

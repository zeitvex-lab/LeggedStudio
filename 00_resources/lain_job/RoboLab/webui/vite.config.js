import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    lib: {
      entry: "src/three-viewer.js",
      formats: ["es"],
      fileName: () => "three-viewer.js",
    },
  },
});

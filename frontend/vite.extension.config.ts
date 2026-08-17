import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

const dirname = import.meta.dirname;

// Separate build for the Chrome/Edge side-panel extension (Tier A). Builds only
// sidepanel.html — the dashboard build (vite.config.ts / `npm run build`) is untouched.
// publicDir points at extension/ instead of the default public/, so manifest.json,
// background.js, and icons/ are copied into dist-extension/ verbatim (not bundled).
export default defineConfig({
  plugins: [react()],
  publicDir: resolve(dirname, "extension"),
  // Relative asset paths — a Chrome extension serves its own files from
  // chrome-extension://<id>/, not a normal web root, so the default absolute base ("/")
  // would emit paths like /assets/index-abc123.js that resolve to nothing there.
  base: "./",
  build: {
    outDir: "dist-extension",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        sidepanel: resolve(dirname, "sidepanel.html"),
      },
    },
  },
});

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Single-Origin im Dev: /api wird an das Backend weitergereicht, damit das
// httpOnly-Refresh-Cookie ohne CORS funktioniert.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://backend:8000",
        // changeOrigin: false -> Host bleibt der des Browsers, damit etwaige
        // Backend-Redirects (Trailing-Slash) nicht auf den internen Host zeigen.
        changeOrigin: false,
      },
    },
  },
});

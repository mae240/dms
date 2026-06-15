import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Single-Origin im Dev: /api wird an das Backend weitergereicht, damit das
// httpOnly-Refresh-Cookie ohne CORS funktioniert.
//
// Hinweis zum test-Block: vitest 2 zieht intern noch vite 5, dessen Typen mit
// vite 6 kollidieren. Daher wird der vitest-Block lokal typisiert und das
// Gesamtobjekt an vite.defineConfig uebergeben (Laufzeit unveraendert).
const test = {
  globals: true,
  environment: "jsdom",
  setupFiles: ["./src/test/setup.ts"],
};

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
  // @ts-expect-error vitest erweitert vite.UserConfig um "test"; die Augmentation
  // wird wegen der doppelten vite-Version (vitest 2 -> vite 5) nicht zuverlaessig
  // geladen. Der Eintrag ist zur Laufzeit gueltig (von vitest gelesen).
  test,
});

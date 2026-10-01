import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies /api to the FastAPI backend, so the browser needs no CORS setup.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { "/api": process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000" },
  },
});

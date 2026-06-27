import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // host: true expõe o dev server fora do container (necessário no Docker).
    host: true,
    proxy: {
      // No Docker o backend fica em http://backend:8000; localmente, localhost.
      "/api": process.env.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
    },
  },
});

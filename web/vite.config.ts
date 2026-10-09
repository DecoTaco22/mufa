import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// La app compilada va dentro del paquete de Python: el mismo servidor la sirve.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/mufa/web",
    emptyOutDir: true,
    // Navegadores de los últimos ~3 años. Con Safari en la lista, el CSS
    // lleva -webkit-backdrop-filter además del estándar (el vidrio).
    cssTarget: ["chrome111", "edge111", "firefox114", "safari16.4"],
  },
  server: {
    // En desarrollo, `npm run dev` y `uv run mufa servidor` en paralelo.
    proxy: { "/api": "http://127.0.0.1:8080" },
  },
});

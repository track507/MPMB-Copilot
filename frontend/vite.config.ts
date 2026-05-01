import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
	server: {
		host: true,
		proxy: {
			"/api": {
				target: "http://127.0.0.1:8000",
				changeOrigin: true,
			},
		},
	},
	build: {
		reportCompressedSize: true,
		chunkSizeWarningLimit: 250,
		rollupOptions: {
			output: {
				manualChunks(id) {
					if (["react", "react-dom", "react-router"].some((pkg) => id.includes(`/node_modules/${pkg}/`))) return "react";
					if (id.includes("/node_modules/@tanstack/")) return "tanstack";
					if (["react-hook-form", "@hookform/resolvers", "zod"].some((pkg) => id.includes(`/node_modules/${pkg}/`))) return "form";
				},
			},
		},
	},
});

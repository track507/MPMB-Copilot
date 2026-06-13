import tailwindcss from "@tailwindcss/vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
	// * React Compiler via the official preset (rolldown babel runner) auto-memoizes components at build time
	// * Targets React 19; the eslint-plugin-react-hooks recommended config enforces the Rules of React the compiler relies on
	plugins: [react(), babel({ presets: [reactCompilerPreset()] }), tailwindcss()],
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

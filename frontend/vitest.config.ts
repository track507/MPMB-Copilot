import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vitest/config";

export default defineConfig({
	plugins: [react()],
	test: {
		globals: true,
		environment: "jsdom",
		setupFiles: ["./test/setup.ts"],
		include: ["test/**/*.{test,spec}.{ts,tsx}"],
		exclude: ["node_modules", "dist"],
		coverage: {
			provider: "v8",
			reporter: ["text", "lcov", "html"],
			reportsDirectory: "./coverage",
			include: ["src/**/*.{ts,tsx}"],
			exclude: ["src/test/**", "src/**/*.d.ts", "src/main.tsx", "src/vite-env.d.ts", "src/components/ui/**"],
			thresholds: {
				lines: 60,
				functions: 60,
				branches: 50,
				statements: 60,
			},
		},
	},
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "./src"),
		},
	},
});

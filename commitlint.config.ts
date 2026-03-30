import type { UserConfig } from "@commitlint/types";

const config: UserConfig = {
	extends: ["@commitlint/config-conventional"],
	rules: {
		"type-enum": [
			2,
			"always",
			[
				"feat", // New feature
				"fix", // Bug fix
				"refactor", // Code change that is not a fix or feature
				"perf", // Performance improvement
				"test", // Adding/updating tests
				"docs", // Documentation only
				"chore", // Build/tooling/dependency changes
				"ci", // CI/CD pipeline changes
				"revert", // Revert a previous commit
				"security", // Security-related changes
			],
		],
		"scope-enum": [
			1, // warn only - don't block commits
			"always",
			[
				"api",
				"chat",
				"health",
				"index",
				"tasks",
				"backend",
				"core",
				"chunker",
				"embeddings",
				"indexer",
				"vector-store",
				"qdrant",
				"rag",
				"model",
				"database",
				"config",
				"logger",
				"scripts",
				"setup",
				"docker",
				"db",
				"data",
				"docs",
				"tests",
				"tooling",
				"deps",
				"repo",
				"ci",
			],
		],
		"subject-case": [2, "always", "sentence-case"],
		"header-max-length": [2, "always", 100],
		"body-max-line-length": [2, "always", 120],
	},
};

export default config;

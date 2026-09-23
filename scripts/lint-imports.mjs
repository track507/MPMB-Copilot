#!/usr/bin/env node
/**
 * Run import-linter's architecture contracts
 *
 * A wrapper exists only to force the subprocess stdio encoding
 * import-linter renders its progress spinner through rich, whose message is a brick emoji
 * On Windows rich falls back to its legacy console renderer, which encodes to cp1252 and raises
 * UnicodeEncodeError before a single contract is evaluated, so the gate fails on a glyph
 *
 * Usage:
 *   pnpm run lint:imports                    all contracts
 *   pnpm run lint:imports -- --verbose       pass extra args through to lint-imports
 */

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// ! pnpm forwards the -- separator itself, and click reads it as a positional argument
const passthrough = process.argv.slice(2).filter((arg) => arg !== "--");

const result = spawnSync("uv", ["--cache-dir", ".uv-cache", "run", "--directory", "backend", "--no-sync", "--group", "dev", "lint-imports", ...passthrough], {
	cwd: REPO_ROOT,
	stdio: "inherit",
	// ? PYTHONIOENCODING is narrower than PYTHONUTF8, which would also change the default open() encoding
	env: { ...process.env, PYTHONIOENCODING: "utf-8" },
	shell: process.platform === "win32",
});

process.exit(result.status ?? 1);

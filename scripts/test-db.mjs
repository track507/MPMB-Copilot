#!/usr/bin/env node
/**
 * Run the database integration suite against a throwaway Postgres.
 *
 * Without TEST_DATABASE_URL the tests/services/db conftest calls pytest.skip, so the
 * suite silently passes while verifying nothing. This builds the URL from .env and
 * runs pytest, so nobody has to remember a shell-specific incantation.
 *
 * Usage:
 *   pnpm run test:db                 all db tests
 *   pnpm run test:db -- -v -k upload pass extra args through to pytest
 */

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TEST_DB = "mpmb_test";

function parseEnv(file) {
	const values = new Map();
	if (!existsSync(file)) return values;

	for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
		const line = raw.trim();
		if (!line || line.startsWith("#")) continue;

		const separator = line.indexOf("=");
		if (separator === -1) continue;

		const key = line.slice(0, separator).trim();
		const value = line
			.slice(separator + 1)
			.trim()
			.replace(/^["']|["']$/g, "");
		values.set(key, value);
	}
	return values;
}

const env = parseEnv(path.join(REPO_ROOT, ".env"));
const user = env.get("POSTGRES_USER") ?? "mpmb_user";
const password = env.get("POSTGRES_PASSWORD") ?? "mpmb_password";
const port = env.get("POSTGRES_HOST_PORT") ?? "5433";

// ! 127.0.0.1 not localhost: localhost can resolve to ::1 first and stall ~20s per
// ! connection before falling back to IPv4, turning a 6s suite into a 7 minute one
// ! pnpm forwards the -- separator itself, and pytest reads it as "every arg after this is a path"
const passthrough = process.argv.slice(2).filter((arg) => arg !== "--");

const url = `postgresql+asyncpg://${user}:${encodeURIComponent(password)}@127.0.0.1:${port}/${TEST_DB}`;

// ! Never point this at the development database: the conftest truncates files, messages and sessions
if (TEST_DB === (env.get("POSTGRES_DB") ?? "mpmb_copilot")) {
	console.error(`Refusing to run: ${TEST_DB} is the development database, and these tests truncate tables.`);
	process.exit(1);
}

console.log(`Database: ${user}@127.0.0.1:${port}/${TEST_DB}`);
console.log(`If this fails to connect, create it first:\n  docker exec mpmb-postgres createdb -U ${user} ${TEST_DB}\n`);

const result = spawnSync(
	"uv",
	["--cache-dir", ".uv-cache", "run", "--no-sync", "--project", "backend", "--group", "dev", "pytest", "backend/tests/services/db", ...passthrough],
	{ cwd: REPO_ROOT, stdio: "inherit", env: { ...process.env, TEST_DATABASE_URL: url }, shell: process.platform === "win32" }
);

process.exit(result.status ?? 1);

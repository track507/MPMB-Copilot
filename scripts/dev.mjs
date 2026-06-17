#!/usr/bin/env node

/**
 * Cross-platform dev startup script.
 *
 * Starts Postgres + Qdrant via Docker, waits for them to be healthy,
 * then launches the backend and frontend dev servers.
 *
 * Usage:
 *   node scripts/dev.mjs        # start everything
 *   pnpm run dev:full            # same, via pnpm script
 */

import { execSync, spawn } from "node:child_process";

const POSTGRES_HOST = "127.0.0.1";
const POSTGRES_PORT = process.env.POSTGRES_HOST_PORT || process.env.POSTGRES_PORT || "5433";
const QDRANT_HOST = "127.0.0.1";
const QDRANT_PORT = process.env.QDRANT_PORT || "6333";

function log(msg) {
	const time = new Date().toLocaleTimeString();
	console.log(`[${time}] ${msg}`);
}

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

function run(cmd, env = {}) {
	try {
		execSync(cmd, {
			stdio: "inherit",
			env: {
				...process.env,
				...env,
			},
		});
		return true;
	} catch {
		return false;
	}
}

async function waitForPort(host, port, label, maxAttempts = 30) {
	for (let i = 1; i <= maxAttempts; i++) {
		try {
			const response = await fetch(`http://${host}:${port}/`).catch(() => null);
			if (response) {
				log(`${label} is ready on port ${port}`);
				return;
			}
		} catch {
			// ignore
		}

		// For postgres, try a TCP connect instead (no HTTP)
		if (label === "Postgres") {
			try {
				const net = await import("node:net");
				const connected = await new Promise((resolve) => {
					const socket = net.createConnection({ host, port: Number(port) }, () => {
						socket.destroy();
						resolve(true);
					});
					socket.on("error", () => resolve(false));
					socket.setTimeout(1000, () => {
						socket.destroy();
						resolve(false);
					});
				});
				if (connected) {
					log(`${label} is ready on port ${port}`);
					return;
				}
			} catch {
				// ignore
			}
		}

		if (i === 1) log(`Waiting for ${label}...`);
		await sleep(2000);
	}

	throw new Error(`${label} did not become ready after ${maxAttempts * 2}s`);
}

// --- Main ---

log("Starting infrastructure services...");

if (!run("docker compose up -d postgres qdrant", { POSTGRES_HOST_PORT: POSTGRES_PORT })) {
	console.error("Failed to start Docker services. Is Docker running?");
	process.exit(1);
}

log("Waiting for services to be healthy...");

await Promise.all([waitForPort(POSTGRES_HOST, POSTGRES_PORT, "Postgres"), waitForPort(QDRANT_HOST, QDRANT_PORT, "Qdrant")]);

log("All services ready. Starting dev servers...\n");

// Spawn with env overrides for localhost.
// Use pnpm run dev which already has the concurrently command configured.
const child =
	process.platform === "win32"
		? spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", "pnpm", "run", "dev"], {
				stdio: "inherit",
				env: {
					...process.env,
					POSTGRES_HOST,
					POSTGRES_PORT,
					QDRANT_HOST,
					QDRANT_PORT,
				},
			})
		: spawn("pnpm", ["run", "dev"], {
				stdio: "inherit",
				env: {
					...process.env,
					POSTGRES_HOST,
					POSTGRES_PORT,
					QDRANT_HOST,
					QDRANT_PORT,
				},
			});

child.on("exit", (code) => {
	process.exit(code ?? 0);
});

// Forward Ctrl+C to child
process.on("SIGINT", () => {
	child.kill("SIGINT");
});

process.on("SIGTERM", () => {
	child.kill("SIGTERM");
});

/**
 * Wait for a backend, then index Qdrant. Used by `pnpm run setup:index`.
 *
 * When nothing is listening on the backend URL, this starts one from backend/.venv
 * and stops it again when indexing finishes. A host backend embeds through whatever
 * ONNX execution provider `inference_device` selects (DirectML/CUDA), while the Linux
 * backend container is CPU-only - that is why setup indexes on the host.
 *
 * Set BACKEND_URL to point at a backend elsewhere; an already-running one is reused
 * as is (authenticated with SERVICE_API_KEY) and never stopped by this script.
 *
 * A backend this script starts itself binds loopback with AUTH_DISABLED=true, so a
 * first-run index works before any admin account exists - a fresh database has no
 * account to mint a SERVICE_API_KEY from. Nothing is persisted: the flag lives on the
 * child process, which is stopped when indexing finishes.
 */

import { spawn, spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { syncChunksToDocker } from "./docker-sync.mjs";
import { AUTH_HINT, authHeaders } from "./service-key.mjs";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const HEALTH_URL = `${BASE_URL}/api/health`;
const INDEX_URL = `${BASE_URL}/api/index`;

const POSTGRES_HOST = process.env.POSTGRES_HOST || "127.0.0.1";
const POSTGRES_PORT = process.env.POSTGRES_HOST_PORT || process.env.POSTGRES_PORT || "5433";
const QDRANT_HOST = process.env.QDRANT_HOST || "127.0.0.1";
const QDRANT_PORT = process.env.QDRANT_PORT || "6333";

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, init = {}) {
	const response = await fetch(url, { ...init, headers: { ...authHeaders(), ...(init.headers || {}) } });
	const text = await response.text();
	let payload = {};

	if (text) {
		try {
			payload = JSON.parse(text);
		} catch {
			payload = { raw: text };
		}
	}

	if (!response.ok) {
		const detail = payload.detail || payload.message || payload.raw || response.statusText;
		const hint = response.status === 401 || response.status === 403 ? ` ${AUTH_HINT}` : "";
		throw new Error(`${init.method || "GET"} ${url} failed: ${response.status} ${detail}${hint}`);
	}

	return payload;
}

async function isBackendUp() {
	try {
		await fetchJson(HEALTH_URL);
		return true;
	} catch {
		return false;
	}
}

function readInferenceDevice() {
	try {
		const settings = JSON.parse(readFileSync(path.join(REPO_ROOT, "data", "settings.json"), "utf8"));
		return settings.inference_device || "cpu";
	} catch {
		return "cpu";
	}
}

function startBackend() {
	const url = new URL(BASE_URL);
	const loopback = url.hostname === "127.0.0.1" || url.hostname === "localhost" || url.hostname === "::1";
	const child = spawn(
		"uv",
		[
			"--cache-dir",
			".uv-cache",
			"run",
			"--no-sync",
			"--project",
			"backend",
			"uvicorn",
			"app.main:app",
			"--app-dir",
			"backend",
			"--host",
			url.hostname,
			"--port",
			url.port || "8000",
		],
		{
			cwd: REPO_ROOT,
			stdio: ["ignore", "inherit", "inherit"],
			// Own process group on POSIX so stopBackend can signal uvicorn too, not just the `uv` wrapper
			detached: process.platform !== "win32",
			env: {
				...process.env,
				// Service addresses win over .env so the host backend reaches the compose stack's published ports
				POSTGRES_HOST,
				POSTGRES_PORT,
				QDRANT_HOST,
				QDRANT_PORT,
				// ! BIND_HOST must mirror --host: the backend honors AUTH_DISABLED only while bound to loopback
				BIND_HOST: url.hostname,
				...(loopback ? { AUTH_DISABLED: "true" } : {}),
			},
		}
	);

	child.on("error", (error) => {
		console.error(`Failed to start the backend: ${error.message}`);
	});

	return child;
}

async function waitForHealth(maxAttempts = 60, delayMs = 2000) {
	for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
		try {
			const health = await fetchJson(HEALTH_URL);
			console.log(`Backend is responding at ${BASE_URL} (status: ${health.status || "unknown"})`);
			return health;
		} catch (error) {
			console.log(`Waiting for backend... (${attempt}/${maxAttempts})`);
			if (attempt === maxAttempts) {
				throw new Error(`Backend did not become ready: ${error.message}`, { cause: error });
			}
			await sleep(delayMs);
		}
	}
}

async function waitForTask(taskId, maxAttempts = 600, delayMs = 3000) {
	let lastProgressLine = "";

	for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
		const task = await fetchJson(`${BASE_URL}/api/tasks/${taskId}`);
		const progress = typeof task.progress === "number" ? ` (${Math.round(task.progress * 100)}%)` : "";
		const message = task.progress_message ? ` ${task.progress_message}` : "";
		const progressLine = `[${task.status}]${progress}${message}`;

		if (progressLine !== lastProgressLine) {
			console.log(progressLine);
			lastProgressLine = progressLine;
		}

		if (task.status === "completed") {
			return task;
		}

		if (task.status === "failed" || task.status === "cancelled") {
			throw new Error(task.error || `Index task ended with status: ${task.status}`);
		}

		if (attempt === maxAttempts) {
			throw new Error("Timed out waiting for indexing to complete");
		}

		await sleep(delayMs);
	}
}

async function triggerIndex() {
	const syncResult = syncChunksToDocker();
	if (syncResult.skipped) {
		console.log(`Skipping Docker chunk sync: ${syncResult.reason}.`);
	} else {
		console.log(`Synced ${syncResult.fileCount} chunk files into ${syncResult.containerName}.`);
	}

	console.log(`Triggering index at ${INDEX_URL} (inference_device: ${readInferenceDevice()})...`);

	const result = await fetchJson(INDEX_URL, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ force_reindex: true }),
	});

	console.log(result.message || "Index request accepted");

	if (!result.task_id) {
		return result;
	}

	return waitForTask(result.task_id);
}

let backend = null;

function stopBackend() {
	if (!backend || backend.exitCode !== null) {
		backend = null;
		return;
	}

	// ! `uv run` execs uvicorn as a grandchild: killing the wrapper alone orphans the python process, which keeps holding the port - a later run would then "reuse" a backend nobody is supervising
	if (process.platform === "win32") {
		spawnSync("taskkill", ["/pid", String(backend.pid), "/T", "/F"], { stdio: "ignore" });
	} else {
		try {
			process.kill(-backend.pid, "SIGTERM");
		} catch {
			backend.kill("SIGTERM");
		}
	}

	backend = null;
}

process.on("SIGINT", () => {
	stopBackend();
	process.exit(130);
});
process.on("SIGTERM", () => {
	stopBackend();
	process.exit(143);
});

try {
	if (await isBackendUp()) {
		console.log(`Reusing the backend already running at ${BASE_URL}.`);
	} else {
		console.log(`No backend at ${BASE_URL}; starting a temporary one from backend/.venv (loopback, auth disabled) for indexing...`);
		backend = startBackend();
	}

	await waitForHealth();
	const finalResult = await triggerIndex();

	if (finalResult?.result) {
		console.log("Indexing complete:", JSON.stringify(finalResult.result, null, 2));
	} else {
		console.log("Indexing complete.");
	}
} catch (error) {
	console.error(error.message);
	stopBackend();
	process.exit(1);
}

stopBackend();

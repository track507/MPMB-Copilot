/**
 * Trigger reindexing against an already-running backend.
 *
 * Unlike wait-and-index.mjs (used during setup), this script fails fast
 * if the backend is not reachable - it does not poll for health.
 *
 * Usage:
 *   node scripts/index.mjs           # index only if Qdrant is empty
 *   node scripts/index.mjs --force   # full reindex regardless
 */

import { syncChunksToDocker } from "./docker-sync.mjs";
import { AUTH_HINT, authHeaders } from "./service-key.mjs";

const BASE_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const INDEX_URL = `${BASE_URL}/api/index`;
const forceReindex = process.argv.includes("--force");

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
		throw new Error(`${init.method || "GET"} ${url}: ${response.status} ${detail}${hint}`);
	}

	return payload;
}

async function waitForTask(taskId) {
	let lastLine = "";

	// Capped embedding threads trade CPU for wall-clock, so a full reindex can run well past 12 min
	for (let attempt = 0; attempt < 600; attempt += 1) {
		const task = await fetchJson(`${BASE_URL}/api/tasks/${taskId}`);
		const pct = typeof task.progress === "number" ? ` (${Math.round(task.progress * 100)}%)` : "";
		const msg = task.progress_message ? ` ${task.progress_message}` : "";
		const line = `[${task.status}]${pct}${msg}`;

		if (line !== lastLine) {
			console.log(line);
			lastLine = line;
		}

		if (task.status === "completed") {
			return task;
		}

		if (task.status === "failed" || task.status === "cancelled") {
			throw new Error(task.error || `Task ended: ${task.status}`);
		}

		await sleep(3000);
	}

	throw new Error("Timed out waiting for indexing to complete");
}

// Main

try {
	const syncResult = syncChunksToDocker();
	if (syncResult.skipped) {
		console.log(`Skipping Docker chunk sync: ${syncResult.reason}.`);
	} else {
		console.log(`Synced ${syncResult.fileCount} chunk files into ${syncResult.containerName}.`);
	}
} catch (error) {
	console.error(`Failed to sync chunk files into Docker: ${error.message}`);
	process.exit(1);
}

// Fail fast if backend is not up
try {
	await fetchJson(`${BASE_URL}/api/health`);
} catch (error) {
	console.error(`Backend is not reachable at ${BASE_URL}: ${error.message}.`);
	console.error("Start the backend first: pnpm run docker:up");
	process.exit(1);
}

console.log(`Triggering ${forceReindex ? "full re-" : ""}index at ${INDEX_URL}...`);

const result = await fetchJson(INDEX_URL, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({ force_reindex: forceReindex }),
});

console.log(result.message || "Index request accepted");

if (result.task_id) {
	const finalResult = await waitForTask(result.task_id);
	if (finalResult?.result) {
		console.log("Done:", JSON.stringify(finalResult.result, null, 2));
	} else {
		console.log("Indexing complete.");
	}
} else {
	console.log("Done.");
}

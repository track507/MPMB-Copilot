import { syncChunksToDocker } from "./docker-sync.mjs";

const BASE_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
const HEALTH_URL = `${BASE_URL}/api/health`;
const INDEX_URL = `${BASE_URL}/api/index`;

function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, init = {}) {
	const response = await fetch(url, init);
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
		throw new Error(`${init.method || "GET"} ${url} failed: ${response.status} ${detail}`);
	}

	return payload;
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

async function waitForTask(taskId, maxAttempts = 240, delayMs = 3000) {
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

	console.log(`Triggering index at ${INDEX_URL}...`);

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

await waitForHealth();
const finalResult = await triggerIndex();

if (finalResult?.result) {
	console.log("Indexing complete:", JSON.stringify(finalResult.result, null, 2));
} else {
	console.log("Indexing complete.");
}

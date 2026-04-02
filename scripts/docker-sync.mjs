import { existsSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";

const DEFAULT_CONTAINER_NAME = process.env.BACKEND_CONTAINER_NAME || "mpmb-backend";
const DEFAULT_CHUNK_DIR = path.resolve(process.cwd(), "data", "chunked_output");

function runDocker(args, { quiet = false } = {}) {
	const result = spawnSync("docker", args, {
		encoding: "utf8",
		stdio: quiet ? "pipe" : ["ignore", "pipe", "pipe"],
	});

	return {
		status: result.status ?? 1,
		stdout: result.stdout || "",
		stderr: result.stderr || "",
		error: result.error,
	};
}

export function isBackendContainerRunning(containerName = DEFAULT_CONTAINER_NAME) {
	const result = runDocker(["inspect", "--format", "{{.State.Running}}", containerName], { quiet: true });
	return result.status === 0 && result.stdout.trim() === "true";
}

export function syncChunksToDocker({
	containerName = DEFAULT_CONTAINER_NAME,
	hostChunkDir = DEFAULT_CHUNK_DIR,
	containerChunkDir = "/app/data/chunked_output",
} = {}) {
	if (!existsSync(hostChunkDir)) {
		throw new Error(`Chunk directory not found: ${hostChunkDir}`);
	}

	const files = readdirSync(hostChunkDir).filter((name) => name.toLowerCase().endsWith(".json"));
	if (files.length === 0) {
		throw new Error(`No JSON chunk files found in ${hostChunkDir}`);
	}

	if (!isBackendContainerRunning(containerName)) {
		return {
			skipped: true,
			reason: `Backend container '${containerName}' is not running`,
			fileCount: files.length,
		};
	}

	const clearResult = runDocker(["exec", containerName, "sh", "-lc", `mkdir -p ${containerChunkDir} && rm -rf ${containerChunkDir}/*`]);

	if (clearResult.status !== 0) {
		throw new Error(clearResult.stderr.trim() || `Failed to prepare ${containerChunkDir} in ${containerName}`);
	}

	const copyResult = runDocker(["cp", `${hostChunkDir}${path.sep}.`, `${containerName}:${containerChunkDir}/`]);
	if (copyResult.status !== 0) {
		throw new Error(copyResult.stderr.trim() || `Failed to copy chunk files to ${containerName}`);
	}

	return {
		skipped: false,
		fileCount: files.length,
		containerName,
		containerChunkDir,
	};
}

/**
 * Service API key lookup for ops scripts
 *
 * Reads SERVICE_API_KEY from the environment, falling back to the repo-root .env file (Node scripts do not load it; the backend reads it via pydantic-settings)
 */
import { readFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export function readServiceKey() {
	if (process.env.SERVICE_API_KEY) return process.env.SERVICE_API_KEY.trim();

	try {
		const env = readFileSync(path.join(REPO_ROOT, ".env"), "utf8");
		for (const line of env.split(/\r?\n/)) {
			const match = /^\s*SERVICE_API_KEY\s*=\s*(.+?)\s*$/.exec(line);
			if (match) return match[1].replace(/^["']|["']$/g, "");
		}
	} catch {
		// satifies the LSP
	}
	return null;
}

export function authHeaders() {
	const key = readServiceKey();
	return key ? { Authorization: `Bearer ${key}` } : {};
}

export const AUTH_HINT = 'Mint a key with "pnpm run mint-key" and set SERVICE_API_KEY in .env, or set AUTH_DISABLED=true for loopback dev.';

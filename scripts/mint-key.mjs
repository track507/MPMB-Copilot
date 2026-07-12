/**
 * Mint a service API key against a running backend
 *
 * Logs in with an admin account, calls POST /api/api-keys, and prints the token exactly once
 * Optionally writes SERVICE_API_KEY into .env
 *
 * Usage:
 *   pnpm run mint-key -- --name "reindex script"
 *   pnpm run mint-key -- --name ops --scopes index:write --expires-days 90 --write-env
 */
import { readFileSync, writeFileSync } from "fs";
import path from "path";
import { createInterface } from "readline";
import { fileURLToPath } from "url";
import { parseArgs } from "util";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASE_URL = (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

const { values: args } = parseArgs({
	options: {
		name: { type: "string", default: "ops script" },
		scopes: { type: "string", default: "index:write" },
		"expires-days": { type: "string" },
		username: { type: "string" },
		"write-env": { type: "boolean", default: false },
	},
});

function prompt(question, { hidden = false } = {}) {
	return new Promise((resolve) => {
		const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
		if (hidden) {
			const write = rl._writeToOutput?.bind(rl);
			rl._writeToOutput = (s) => {
				if (s.includes(question)) write(s);
			};
		}
		rl.question(question, (answer) => {
			rl.close();
			if (hidden) process.stdout.write("\n");
			resolve(answer.trim());
		});
	});
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
		throw new Error(`${init.method || "GET"} ${url}: ${response.status} ${detail}`);
	}
	return { payload, response };
}

function upsertEnvKey(token) {
	const envPath = path.join(REPO_ROOT, ".env");
	const content = readFileSync(envPath, "utf8");
	const line = `SERVICE_API_KEY=${token}`;
	const next = /^\s*SERVICE_API_KEY\s*=.*$/m.test(content)
		? content.replace(/^\s*SERVICE_API_KEY\s*=.*$/m, line)
		: `${content.replace(/\n?$/, "\n")}${line}\n`;
	writeFileSync(envPath, next);
}

const username = args.username || (await prompt("Admin username: "));
const password = await prompt("Admin password: ", { hidden: true });

const { response: loginResponse } = await fetchJson(`${BASE_URL}/api/auth/login`, {
	method: "POST",
	headers: { "Content-Type": "application/json" },
	body: JSON.stringify({ username, password }),
});

const cookie = (loginResponse.headers.getSetCookie?.() || []).map((c) => c.split(";")[0]).find((c) => c.startsWith("mpmb_session="));
if (!cookie) {
	console.error("Login succeeded but no session cookie was returned.");
	process.exit(1);
}

const body = {
	name: args.name,
	scopes: args.scopes
		.split(",")
		.map((s) => s.trim())
		.filter(Boolean),
};
if (args["expires-days"]) body.expires_days = Number(args["expires-days"]);

const { payload: key } = await fetchJson(`${BASE_URL}/api/api-keys`, {
	method: "POST",
	headers: { "Content-Type": "application/json", Cookie: cookie },
	body: JSON.stringify(body),
});

console.log(`\nMinted "${key.name}" (${key.token_prefix}...) with scopes: ${key.scopes.join(", ")}`);
console.log("\nThis token is shown ONCE. Add it to .env:\n");
console.log(`SERVICE_API_KEY=${key.token}\n`);

if (args["write-env"]) {
	upsertEnvKey(key.token);
	console.log("Wrote SERVICE_API_KEY to .env.");
}

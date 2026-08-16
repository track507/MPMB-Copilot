#!/usr/bin/env node

/**
 * Prepare the local environment and rebuild the chunked MPMB corpus
 *
 * 1. Creates .env from .env.example when missing
 * 2. Resolves source paths from environment variables or .env
 * 3. Installs backend Python dependencies with uv (skip with --sku=ip-dependencies)
 * 4. Reports the ONNX execution provider and, on virst run, opts into a GPU inference
 * 5. Clones or updates the required repos
 * 6. Runs the source analyzer, then scripts/chunk_mpmb.py in the backend environment
 *
 * This doesn't build docker, start services, or trigger indexing
 *
 * Usage: pn run setup [--skip-dependencies] [--dry-run]
 */

// ! Temporal has no Node runtime (V8 ships none through Node 24); install the global polyfill before any use
import "temporal-polyfill/global";
import { spawnSync } from "child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ENV_FILE = path.join(ROOT, ".env");
const ENV_EXAMPLE = path.join(ROOT, ".env.example");
const BACKEND_DIR = path.join(ROOT, "backend");
const CHUNK_SCRIPT = path.join(ROOT, "scripts", "chunk_mpmb.py");
const UV_CACHE = ".uv-cache";

const skipDependencies = process.argv.includes("--skip-dependencies");
const dryRun = process.argv.includes("--dry-run");

// ANSI escape sequences for colored output
// * Yes I know that not every terminal supports this
const COLOR = { INFO: "", SUCCESS: "\u001b[32m", WARNING: "\u001b[33m", ERROR: "\u001b[31m", DIM: "\u001b[90m" };
const RESET = "\u001b[0m";

function log(message, level = "INFO") {
	const stamp = Temporal.Now.plainDateTimeISO().toString({ smallestUnit: "second" }).replace("T", " ");
	console.log(`${COLOR[level]}[${stamp}] [${level}] ${message}${level === "INFO" ? "" : RESET}`);
}

function hint(message) {
	console.log(`${COLOR.DIM}   ${message}${RESET}`);
}

function commandExists(command) {
	const probe = process.platform === "win32" ? "where" : "which";
	return spawnSync(probe, [command], { stdio: "ignore" }).status === 0;
}

function needsShell(file) {
	return process.platform === "win32" && !/\.(exe|com)$/i.test(file);
}

function run(file, args, { cwd = ROOT, allowFail = false } = {}) {
	const result = needsShell(file)
		? spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", file, ...args], { cwd, stdio: "inherit" })
		: spawnSync(file, args, { cwd, stdio: "inherit" });

	if (result.status !== 0 && !allowFail) {
		throw new Error(`Command failed: ${file} ${args.join(" ")}`);
	}

	return result.status ?? 1;
}

function capture(file, args, { cwd = ROOT } = {}) {
	const result = needsShell(file)
		? spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", file, ...args], { cwd, encoding: "utf8" })
		: spawnSync(file, args, { cwd, encoding: "utf8" });
	return { status: result.status ?? 1, stdout: (result.stdout || "").trim(), stderr: (result.stderr || "").trim() };
}

function act(description, fn) {
	if (dryRun) {
		log(`What if: ${description}`, "WARNING");
		return false;
	}
	fn();
	return true;
}

function parseEnv(file) {
	const values = new Map();
	if (!existsSync(file)) return values;

	for (const raw of readFileSync(file, "utf8").split(/\r?\n/)) {
		const line = raw.trim();
		if (!line || line.startsWith("#")) continue;

		const separator = line.indexOf("=");
		if (separator < 1) continue;

		let value = line.slice(separator + 1).trim();
		if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith('"') && value.endsWith('"'))) {
			value = value.slice(1, -1);
		}
		values.set(line.slice(0, separator).trim(), value);
	}

	return values;
}

function setting(name, fallback, env) {
	const fromProcess = process.env[name];

	if (fromProcess !== undefined && fromProcess.trim() !== "") return fromProcess;

	const fromFile = env.get(name);
	if (fromFile !== undefined && fromFile.trim() !== "") return fromFile;

	return fallback;
}

function projectPath(value) {
	return path.isAbsolute(value) ? path.resolve(value) : path.resolve(ROOT, value);
}

function ensureDir(dir) {
	if (existsSync(dir)) return;
	act(`Create directory ${dir}`, () => {
		mkdirSync(dir, { recursive: true });
	});
}

function initializeEnvFile() {
	if (existsSync(ENV_FILE)) return;

	if (!existsSync(ENV_EXAMPLE)) {
		log("No .env and no .env.example found to seed it from; docker compose needs a .env.", "WARNING");
		return;
	}

	log("No .env found. Creating one from .env.example");

	const seeded = readFileSync(ENV_EXAMPLE, "utf8")
		.split(/\r?\n/)
		.map((line) =>
			line
				.replace(/^(?<key>POSTGRES_HOST=)postgres(?=\s|$)/, "$<key>127.0.0.1")
				.replace(/^(?<key>POSTGRES_PORT=)5432(?=\s|$)/, "$<key>5433")
				.replace(/^(?<key>QDRANT_HOST=)qdrant(?=\s|$)/, "$<key>127.0.0.1")
		)
		.join("\n");

	act(`Create ${ENV_FILE} from .env.example`, () => {
		writeFileSync(ENV_FILE, seeded, "utf8");
		log(`Created ${ENV_FILE} - add your ANTHROPIC_API_KEY before starting the app.`, "WARNING");
	});
}

function installPythonDependencies() {
	const syncArgs = ["--cache-dir", UV_CACHE, "sync", "--project", BACKEND_DIR];

	if (!existsSync(path.join(BACKEND_DIR, "uv.lock"))) {
		log("No backend/uv.lock found; resolving dependencies and writing one", "WARNING");
		act("Lock and install backend dependencies", () => {
			run("uv", syncArgs);
		});
		return;
	}

	// * `--locked` installs exactly what uv.lock pins and fails if pyproject.toml drifted, so a routine run cannot re-resolve
	act("Install backend dependencies from uv.lock", () => {
		if (run("uv", [...syncArgs, "--locked"], { allowFail: true }) === 0) return;

		log("backend/uv.lock does not match backend/pyproject.toml; re-locking", "WARNING");
		run("uv", syncArgs);
		log("backend/uv.lock was updated - commit it so everyone installs the same versions", "WARNING");
	});
}

function gpuProviderLabel() {
	const probe = "from app.core.onnx_device import detect_gpu_provider; d = detect_gpu_provider(); print(d[1] if d else '')";
	const result = capture("uv", ["--cache-dir", UV_CACHE, "run", "--no-sync", "--project", BACKEND_DIR, "python", "-c", probe]);

	if (result.status !== 0) return null;

	const label = result.stdout
		.split(/\r?\n/)
		.map((line) => line.trim())
		.filter(Boolean)
		.at(-1);

	return label || null;
}

function initializeInferenceDevice(settingsPath) {
	const label = gpuProviderLabel();
	if (!label) {
		log("No GPU execution provider found; embedding and reranking will run on CPU", "WARNING");
		hint("To add one: pnpm run gpu:install");
		return;
	}

	log(`GPU execution provider available: ${label}`, "SUCCESS");

	let settings = {};
	if (existsSync(settingsPath)) {
		try {
			settings = JSON.parse(readFileSync(settingsPath, "utf8"));
		} catch {
			log(`Could not parse ${settingsPath}; leaving it untouched`, "WARNING");
			return;
		}
	}

	// ! Never overwrite a deliberate choice: only an absent key gets the detected default
	if (Object.hasOwn(settings, "inference_device")) {
		if (settings.inference_device === "gpu") {
			log("inference_device is already 'gpu'.");
		} else {
			log(
				`inference_device is '${String(settings.inference_device)}'; leaving it as is. Switch it in Settings -> Compute device to use ${label}`,
				"WARNING"
			);
		}
		return;
	}

	settings.inference_device = "gpu";
	act(`Set inference_device to gpu in ${settingsPath}`, () => {
		writeFileSync(settingsPath, `${JSON.stringify(settings, null, 2)}\n`, "utf8");
		log(`Set inference_device to 'gpu' in ${settingsPath}`, "SUCCESS");
	});
}

const PLACEHOLDERS = new Set([".gitkeep", ".gitignore", "README.md"]);

function normalizeGitUrl(url) {
	const trimmed = (url || "").trim().replace(/\/+$/, "");
	return (trimmed.endsWith(".git") ? trimmed.slice(0, -4) : trimmed).toLowerCase();
}

function git(repoDir, args) {
	const result = capture("git", ["-C", repoDir, ...args]);
	if (result.status !== 0) return null;
	return result.stdout
		.split(/\r?\n/)
		.filter((line) => line && !line.startsWith("warning:"))
		.join("\n")
		.trim();
}

function enableGitSafeDirectory(repoDir) {
	const resolved = path.resolve(repoDir);
	const configured = capture("git", ["config", "--global", "--get-all", "safe.directory"]);
	const normalized = resolved.replace(/\\/g, "/").toLowerCase();

	if (configured.status === 0 && configured.stdout.split(/\r?\n/).some((line) => line.trim().replace(/\\/g, "/").toLowerCase() === normalized)) {
		return;
	}

	log(`Adding Git safe.directory for ${resolved}`);
	act(`Add Git safe.directory entry for ${resolved}`, () => {
		run("git", ["config", "--global", "--add", "safe.directory", resolved]);
	});
}

function syncGitRepository({ name, url, targetDir, branch, allowRemoteRetarget = false }) {
	let shouldClone = !existsSync(targetDir);

	if (existsSync(targetDir) && !existsSync(path.join(targetDir, ".git"))) {
		const entries = readdirSync(targetDir);
		const real = entries.filter((entry) => !PLACEHOLDERS.has(entry));
		if (real.length > 0) {
			throw new Error(`${name} target exists but is not a git repository and contains files: ${targetDir} (${real.join(", ")})`);
		}

		if (entries.length > 0) {
			log(`${name} target only contains placeholder files; preparing it for clone`);
			for (const entry of entries) {
				act(`Remove placeholder ${entry} before cloning ${name}`, () => {
					rmSync(path.join(targetDir, entry), { force: true, recursive: true });
				});
			}
		}
		shouldClone = true;
	}

	if (shouldClone) {
		ensureDir(path.dirname(targetDir));
		const cloneArgs = ["clone", ...(branch ? ["--branch", branch, "--single-branch"] : []), url, targetDir];
		log(`Cloning ${name}...`);
		act(`Clone ${name}`, () => {
			run("git", cloneArgs);
		});
	} else {
		enableGitSafeDirectory(targetDir);

		const origin = git(targetDir, ["remote", "get-url", "origin"]);
		if (origin === null) throw new Error(`Unable to read origin URL for ${name} at ${targetDir}`);

		if (normalizeGitUrl(origin) !== normalizeGitUrl(url)) {
			if (!allowRemoteRetarget) throw new Error(`${name} target points at a different repository: ${origin}`);
			log(`${name} target points at ${origin}; retargeting origin to ${url}`);
			act(`Retarget origin for ${name}`, () => {
				run("git", ["-C", targetDir, "remote", "set-url", "origin", url]);
				run("git", ["-C", targetDir, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"]);
			});
		}

		const status = git(targetDir, ["status", "--short"]);
		if (status) {
			log(`${name} has local changes; skipping update to avoid overwriting them`, "WARNING");
			log(`Continuing with the existing checkout for ${name}`);
		} else {
			log(`Updating ${name}...`);
			try {
				act(`Update ${name}`, () => {
					run("git", ["-C", targetDir, "fetch", "--all", "--prune"]);
					if (branch) {
						run("git", ["-C", targetDir, "checkout", branch]);
						run("git", ["-C", targetDir, "pull", "--ff-only", "origin", branch]);
					} else {
						run("git", ["-C", targetDir, "pull", "--ff-only"]);
					}
				});
			} catch (error) {
				// ! A non-fast-forward must not fail setup; the existing checkout is still usable
				log(`Unable to update ${name} cleanly; continuing with the existing checkout`, "WARNING");
				log(error.message, "WARNING");
			}
		}
	}

	if (existsSync(path.join(targetDir, ".git"))) {
		enableGitSafeDirectory(targetDir);
		const head = git(targetDir, ["rev-parse", "--abbrev-ref", "HEAD"]);
		const commit = git(targetDir, ["rev-parse", "--short", "HEAD"]);
		log(head && commit ? `${name} ready at ${head} (${commit})` : `${name} ready at ${targetDir}`, "SUCCESS");
	}
}

console.log("");
console.log("MPMB source setup");
console.log(`Project root: ${ROOT}`);
console.log("");

if (!commandExists("git")) {
	log("Git is required but was not found in PATH.", "ERROR");
	process.exit(1);
}

if (!commandExists("uv")) {
	log("uv is required but was not found in PATH.", "ERROR");
	hint("Install it, then re-run this script:");
	hint("https://docs.astral.sh/uv/getting-started/installation/");
	// ? Only Windows gets the winget line; the .ps1 printed it on every platform
	if (process.platform === "win32") hint("winget install --id=astral-sh.uv -e");
	process.exit(1);
}

// * The chunker reads the analyzer report, and the analyzer is a pnpm workspace package
if (!commandExists("pnpm")) {
	log("pnpm is required but was not found in PATH.", "ERROR");
	hint("Install it, then re-run this script: https://pnpm.io/installation");
	process.exit(1);
}

initializeEnvFile();

const env = parseEnv(ENV_FILE);
const dataDir = projectPath(setting("DATA_DIR", "./data", env));
const mpmbSourceDir = projectPath(setting("MPMB_SOURCE_DIR", "./data/mpmb_source", env));
const mpmbSource2024Dir = projectPath(setting("MPMB_SOURCE_2024_DIR", "./data/mpmb_source_2024", env));
const importsSourceDir = projectPath(setting("IMPORTS_SOURCE_DIR", "./data/imports_source", env));
const chunkedOutputDir = projectPath(setting("CHUNKED_OUTPUT_DIR", "./data/chunked_output", env));

const mpmbRepoUrl = setting("MPMB_REPO_URL", "https://github.com/morepurplemorebetter/MPMBs-Character-Record-Sheet.git", env);
const mpmbRepo2024Url = setting("MPMB_REPO_2024_URL", "https://github.com/morepurplemorebetter/2024_MPMBs-Character-Record-Sheet.git", env);
const branch2014 = setting("MPMB_REPO_BRANCH_2014", "master", env);
const branch2024 = setting("MPMB_REPO_BRANCH_2024", "main", env);
const importsRepoUrl = setting("IMPORTS_REPO_URL", "https://github.com/safety-orange/Imports-for-MPMB-s-Character-Sheet.git", env);

log("Using source paths:");
hint(`2014 repo:  ${mpmbSourceDir}`);
hint(`2024 repo:  ${mpmbSource2024Dir}`);
hint(`Imports:    ${importsSourceDir}`);
hint(`Chunks:     ${chunkedOutputDir}`);
console.log("");

ensureDir(dataDir);
ensureDir(chunkedOutputDir);
ensureDir(path.join(dataDir, "index_cache"));
ensureDir(path.join(dataDir, "uploads"));

try {
	if (skipDependencies) {
		log("Skipping the backend dependency install (--skip-dependencies)", "WARNING");
	} else {
		log("Installing backend Python dependencies with uv...");
		installPythonDependencies();
		log(`Backend environment ready at ${path.join(BACKEND_DIR, ".venv")}`, "SUCCESS");
	}

	initializeInferenceDevice(path.join(dataDir, "settings.json"));

	syncGitRepository({ name: "MPMB main repo (2014)", url: mpmbRepoUrl, targetDir: mpmbSourceDir, branch: branch2014 });
	syncGitRepository({ name: "MPMB main repo (2024)", url: mpmbRepo2024Url, targetDir: mpmbSource2024Dir, branch: branch2024, allowRemoteRetarget: true });
	syncGitRepository({ name: "Imports repo", url: importsRepoUrl, targetDir: importsSourceDir, branch: "" });

	log("Running the source analyzer...");
	// ! The chunker hard-fails without scripts/analyze/reports/mpmb-analysis.json, rebuilt from the trees just updated
	act("Run the source analyzer", () => {
		run("pnpm", ["run", "analyze"]);
	});

	log("Starting chunker...");
	act("Run the MPMB chunker", () => {
		run("uv", ["--cache-dir", UV_CACHE, "run", "--no-sync", "--project", BACKEND_DIR, "python", CHUNK_SCRIPT]);
	});

	log("Setup complete", "SUCCESS");
} catch (error) {
	log(error.message, "ERROR");
	process.exit(1);
}

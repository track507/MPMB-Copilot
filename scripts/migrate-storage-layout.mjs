#!/usr/bin/env node
/**
 * Regroup data/ into the three lifecycles: packs reinstall, runtime is disposable, tenants must be backed up
 *
 * Dry run by default, because this moves gigabytes and the corpus directories are git clones
 * Idempotent: a second run reports everything as already moved and changes nothing
 *
 * Usage:
 *   node scripts/migrate-storage-layout.mjs            plan only, moves nothing
 *   node scripts/migrate-storage-layout.mjs --apply    performs the moves
 */

import { existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmdirSync, statSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DATA = path.join(REPO_ROOT, "data");
const CONFIG = path.join(REPO_ROOT, "backend", "app", "config.py");
const apply = process.argv.includes("--apply");

/**
 * Source to destination, both relative to data/
 *
 * ! This table and backend/app/config.py must agree
 */
const MOVES = [
	["mpmb_source", "packs/mpmb/source_2014"],
	["mpmb_source_2024", "packs/mpmb/source_2024"],
	["imports_source", "packs/mpmb/imports"],
	["adobe_docs", "packs/mpmb/adobe_docs"],
	["mpmb_pdfs", "packs/mpmb/pdfs"],
	["mpmb_character_sheets", "packs/mpmb/character_sheets"],
	["models", "runtime/models"],
	["chunked_output", "runtime/chunked_output"],
	["index_cache", "runtime/index_cache"],
	["extracted", "runtime/extracted"],
];

// ! Removed rather than moved: prefix existence carries no meaning, and an object store cannot represent an empty one
const PRUNE = ["uploads/session", "uploads/global", "uploads/shared", "uploads"];

/** @param {string} p @returns {number} */
function deviceOf(p) {
	// ? Stat the nearest existing ancestor, since a destination does not exist yet
	let probe = p;
	while (!existsSync(probe)) probe = path.dirname(probe);
	return statSync(probe).dev;
}

/**
 * True when a directory tree holds directories and nothing else
 *
 * ! A single file anywhere below makes this false, so the prune can never delete real content
 * @param {string} p @returns {boolean}
 */
function isEmptyTree(p) {
	if (!statSync(p).isDirectory()) return false;
	return readdirSync(p, { withFileTypes: true }).every((entry) => entry.isDirectory() && isEmptyTree(path.join(p, entry.name)));
}

/**
 * Remove a tree of empty directories, deepest first
 *
 * @param {string} p @returns {number} how many directories were removed
 */
function pruneEmptyTree(p) {
	let removed = 0;
	for (const entry of readdirSync(p, { withFileTypes: true })) {
		if (entry.isDirectory()) removed += pruneEmptyTree(path.join(p, entry.name));
	}
	rmdirSync(p);
	return removed + 1;
}

/** @returns {{from: string, to: string, status: string, note: string}[]} */
function plan() {
	return MOVES.map(([from, to]) => {
		const src = path.join(DATA, from);
		const dst = path.join(DATA, to);
		const srcExists = existsSync(src);
		const dstExists = existsSync(dst);

		if (!srcExists && dstExists) return { from, to, status: "done", note: "already moved" };
		if (!srcExists) return { from, to, status: "skip", note: "nothing at the source" };
		if (dstExists) return { from, to, status: "blocked", note: "destination already exists" };

		// ! A rename across volumes throws EXDEV; falling back to a copy would turn 3.5 GB into a long silent stall
		if (deviceOf(src) !== deviceOf(dst)) {
			return { from, to, status: "blocked", note: "source and destination are on different volumes" };
		}
		return { from, to, status: "move", note: "" };
	});
}

/**
 * Refuse when config still names a directory this script is about to move
 *
 * ! This is the failure that costs the most: the bytes move, the app keeps reading the old path and rebuilds silently
 * @returns {string[]}
 */
function staleConfigPaths() {
	const config = readFileSync(CONFIG, "utf8");
	return MOVES.map(([from]) => `"./data/${from}`).filter((needle) => config.includes(needle));
}

function main() {
	const actions = plan();
	const stale = staleConfigPaths();

	console.log(`Repo: ${REPO_ROOT}`);
	for (const { from, to, status, note } of actions) {
		const arrow = status === "move" ? "->" : "  ";
		console.log(`  [${status.padEnd(7)}] data/${from.padEnd(24)} ${arrow} data/${to}${note ? `   (${note})` : ""}`);
	}

	for (const rel of PRUNE) {
		const p = path.join(DATA, rel);
		if (!existsSync(p)) continue;
		const empty = isEmptyTree(p);
		console.log(`  [${empty ? "prune  " : "KEEP   "}] data/${rel}${empty ? "" : "   (holds files)"}`);
	}

	const blocked = actions.filter((a) => a.status === "blocked");
	if (blocked.length) {
		console.error(`\nRefusing to run: ${blocked.length} destination(s) are not safe to write.`);
		return 1;
	}
	if (stale.length) {
		console.error(`\nRefusing to run: backend/app/config.py still points at ${stale.join(", ")}`);
		console.error("Repoint config first, or the move completes and the app keeps reading the old location.");
		return 1;
	}

	const moves = actions.filter((a) => a.status === "move");
	if (!moves.length) {
		console.log("\nNothing to move.");
	} else if (!apply) {
		console.log(`\nDry run. Re-run with --apply to move ${moves.length} directories.`);
		return 0;
	}

	for (const { from, to } of moves) {
		const dst = path.join(DATA, to);
		mkdirSync(path.dirname(dst), { recursive: true });
		renameSync(path.join(DATA, from), dst);
		console.log(`moved data/${from} -> data/${to}`);
	}

	for (const rel of PRUNE) {
		const p = path.join(DATA, rel);
		// ! Only ever removes directories, so a stray upload stops the prune instead of being deleted
		if (existsSync(p) && isEmptyTree(p)) {
			console.log(`pruned ${pruneEmptyTree(p)} empty directories under data/${rel}`);
		}
	}

	console.log("\nDone. Run pnpm run check, then start the backend and confirm retrieval still answers.");
	return 0;
}

process.exitCode = main();

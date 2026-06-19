import { execFileSync } from "node:child_process";
import path from "node:path";
import fg from "fast-glob";
import type { RepoConfig, RepoProvenance } from "./types";

export const REPOS: RepoConfig[] = [
	{ key: "mpmb_source", dir: "data/mpmb_source", edition: "2014", kind: "mpmb" },
	{ key: "mpmb_source_2024", dir: "data/mpmb_source_2024", edition: "2024", kind: "mpmb" },
	{ key: "imports_source", dir: "data/imports_source", edition: "auto", kind: "imports" },
];

export const SKIP_NAMES = new Set(["gulpfile.js", "package.json", "package-lock.json"]);

// ! minified WotC bundles (all_WotC_*.min.js) are one giant line re-declaring every WotC object - parsing them duplicates the real per-book sources
export function isSkippedFile(rel: string): boolean {
	const name = path.basename(rel);
	if (SKIP_NAMES.has(name)) return true;
	if (name.endsWith(".min.js")) return true;
	return /^all_WotC_.*\.js$/.test(name);
}

export async function listFiles(repoDir: string): Promise<string[]> {
	const rels = await fg("**/*.js", { cwd: repoDir, dot: false, absolute: false });
	return rels.filter((rel) => !isSkippedFile(rel)).sort();
}

export function gitProvenance(repoDir: string): RepoProvenance {
	const run = (args: string[]): string => {
		try {
			// ? explicit utf8 so Unicode commit subjects render on Windows
			return execFileSync("git", args, { cwd: repoDir, encoding: "utf8" }).trim();
		} catch {
			return "";
		}
	};
	const commit = run(["rev-parse", "HEAD"]) || "unknown";
	return {
		branch: run(["rev-parse", "--abbrev-ref", "HEAD"]) || "unknown",
		commit,
		short_commit: commit === "unknown" ? "unknown" : commit.slice(0, 9),
		date: run(["log", "-1", "--format=%cI"]) || "unknown",
		subject: run(["log", "-1", "--format=%s"]) || "unknown",
		refs: run(["log", "-1", "--format=%D"]) || "",
		remote: run(["config", "--get", "remote.origin.url"]) || "",
	};
}

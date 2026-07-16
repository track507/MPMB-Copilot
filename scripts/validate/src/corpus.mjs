import { readdirSync, readFileSync } from "fs";
import path from "path";
import { lint, loadGlobals } from "./lint.mjs";

const ROOT = path.resolve(import.meta.dirname, "../../..");

// * Genuine post-ES5 code shipped in the corpora, waived here so the ES5 bans stay errors for generated scripts
// * Entries are [path suffix with forward slashes, ruleId]
const BASELINE = [
	["/_functions/Functions0.js", "no-restricted-properties"], // ? Object.assign polyfill guard
	["/_functions/Functions0.js", "no-restricted-syntax"], // ? spread inside a try with an ES5 catch-fallback
	["/_functions/FunctionsSpells.js", "no-restricted-syntax"], // ? bare arrow callbacks in reduce/sort
	["/Kibbles Compendium of Craft and Creation (v1.1.3).js", "no-restricted-syntax"], // ? 3rd-party arrows and default params
];

/**
 * @param {string} file
 * @param {string} ruleId
 */
function isBaselined(file, ruleId) {
	const fwd = file.replaceAll("\\", "/");
	return BASELINE.some(([suffix, rule]) => ruleId === rule && fwd.endsWith(suffix));
}

/** @param {string} rel */
function isSkipped(rel) {
	const segs = rel.split(/[\\/]/);
	// * dependency and VCS trees appear when --extra points at an external repo checkout
	if (segs.includes("node_modules") || segs.includes(".git")) return true;
	// * the syntax templates are documentation pseudo-code, deliberately not parseable
	if (segs.includes("additional content syntax")) return true;
	const name = path.basename(rel);
	// Skip the gulp/minimized files
	if (name === "gulpfile.js") return true;
	if (name.endsWith(".min.js")) return true;
	// all_WotC_ is built by gulp is an accumulation of all files
	return /^all_WotC_.*\.js$/.test(name);
}

/** @param {string} dir */
function jsFiles(dir) {
	return readdirSync(dir, { recursive: true, encoding: "utf8" })
		.filter((rel) => rel.endsWith(".js") && !isSkipped(rel))
		.map((rel) => path.join(dir, rel))
		.sort();
}

/**
 * @param {string[]} argv
 * @returns {{ dir: string, edition: string }[]}
 */
function parseTargets(argv) {
	const targets = [
		{ dir: path.join(ROOT, "data/mpmb_source"), edition: "2014" },
		{ dir: path.join(ROOT, "data/mpmb_source_2024"), edition: "2024" },
	];
	for (let i = 0; i < argv.length; i++) {
		if (argv[i] === "--extra") {
			targets.push({ dir: path.resolve(argv[i + 1]), edition: argv[i + 2] });
			i += 2;
		}
	}
	return targets;
}

const globalsData = loadGlobals();
/** @type {Map<string, number>} */
const ruleCounts = new Map();
/** @type {Map<string, number>} */
const unknownNames = new Map();
let files = 0;
let errorTotal = 0;

for (const target of parseTargets(process.argv.slice(2))) {
	for (const file of jsFiles(target.dir)) {
		files++;
		const { findings } = lint(readFileSync(file, "utf8"), target.edition, globalsData);
		for (const f of findings) {
			if (f.severity !== "error" || isBaselined(file, f.ruleId)) continue;
			errorTotal++;
			ruleCounts.set(f.ruleId, (ruleCounts.get(f.ruleId) ?? 0) + 1);
			const undef = /^'(.+)' is not defined/.exec(f.message);
			if (undef) unknownNames.set(undef[1], (unknownNames.get(undef[1]) ?? 0) + 1);
			if (errorTotal <= 40) console.log(`${path.relative(ROOT, file)}:${f.line}:${f.column} [${f.ruleId}] ${f.message}`);
		}
	}
}

/** @param {Map<string, number>} map */
const top = (map) => Object.fromEntries([...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40));
console.log(`\n${files} files, ${errorTotal} errors`);
if (ruleCounts.size) console.log("errors by rule:", top(ruleCounts));
if (unknownNames.size) console.log("top unknown names (override candidates):", top(unknownNames));
process.exitCode = errorTotal === 0 ? 0 : 1;

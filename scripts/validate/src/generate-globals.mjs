import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

/**
 * @typedef {{ registries: string[], functions: string[] }} EngineSurfaceJson
 * @typedef {{
 *   engine_surface_by_repo?: Record<string, EngineSurfaceJson>,
 *   implicit_globals?: { repo: string, name: string, classification?: string }[],
 *   undeclared_by_repo?: Record<string, string[]>,
 * }} AnalyzerReport
 * @typedef {"2014" | "2024"} Edition
 * @typedef {{ common: string[], "2014": string[], "2024": string[] }} GlobalsSets
 * @typedef {Record<string, { add?: string[], remove?: string[] }>} Overrides
 */

// ! Engine repos only: names attested solely by third-party imports are promoted via overrides, never auto-trusted
/** @type {Record<string, Edition>} */
const EDITION_REPOS = { mpmb_source: "2014", mpmb_source_2024: "2024" };

/**
 * @param {AnalyzerReport} report
 * @param {Overrides} overrides
 * @returns {GlobalsSets}
 */
export function buildGlobals(report, overrides) {
	/** @type {Record<Edition, Set<string>>} */
	const byEdition = { 2014: new Set(), 2024: new Set() };

	for (const [repoKey, edition] of Object.entries(EDITION_REPOS)) {
		const surface = report.engine_surface_by_repo?.[repoKey];
		if (!surface) throw new Error(`report missing engine_surface_by_repo.${repoKey} - re-run the analyzer first`);
		for (const name of [...surface.registries, ...surface.functions]) byEdition[edition].add(name);
	}

	// * host-write and leak-candidate globals both exist at sheet runtime
	for (const entry of report.implicit_globals ?? []) {
		const edition = EDITION_REPOS[entry.repo];
		if (edition) byEdition[edition].add(entry.name);
	}

	// * engine code referencing an undeclared name attests it exists in the PDF runtime layer
	for (const [repoKey, edition] of Object.entries(EDITION_REPOS)) {
		for (const name of report.undeclared_by_repo?.[repoKey] ?? []) byEdition[edition].add(name);
	}

	const common = [...byEdition["2014"]].filter((n) => byEdition["2024"].has(n)).sort();
	const commonSet = new Set(common);
	/** @type {GlobalsSets} */
	const result = {
		common,
		2014: [...byEdition["2014"]].filter((n) => !commonSet.has(n)).sort(),
		2024: [...byEdition["2024"]].filter((n) => !commonSet.has(n)).sort(),
	};

	for (const [set, ops] of Object.entries(overrides)) {
		if (!(set in result)) throw new Error(`overrides: unknown set "${set}"`);
		const key = /** @type {keyof GlobalsSets} */ (set);
		const names = new Set(result[key]);
		for (const name of ops.add ?? []) names.add(name);
		for (const name of ops.remove ?? []) names.delete(name);
		result[key] = [...names].sort();
	}
	return result;
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
	const root = path.resolve(import.meta.dirname, "../../..");
	const report = JSON.parse(readFileSync(path.join(root, "scripts/analyze/reports/mpmb-analysis.json"), "utf8"));
	const overrides = JSON.parse(readFileSync(path.join(import.meta.dirname, "../globals.overrides.json"), "utf8"));
	const generated = buildGlobals(report, overrides);
	const out = path.join(import.meta.dirname, "../globals.generated.json");
	writeFileSync(out, JSON.stringify(generated, null, "\t") + "\n", "utf8");
	console.log(`Wrote ${out}: common=${generated.common.length} 2014=${generated["2014"].length} 2024=${generated["2024"].length}`);
}

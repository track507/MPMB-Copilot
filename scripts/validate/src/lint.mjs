// The linter core: lint(source, edition) -> findings
import { readFileSync } from "node:fs";
import path from "node:path";
import { Linter } from "eslint";
import { buildConfig } from "./acrojs-config.mjs";

/** @typedef {import("./generate-globals.mjs").GlobalsSets} GlobalsSets */
/**
 * @typedef {{
 *   line: number,
 *   column: number,
 *   ruleId: string,
 *   severity: "error" | "warning",
 *   message: string,
 * }} Finding
 */

const GENERATED = path.join(import.meta.dirname, "..", "globals.generated.json");
const EDITIONS = new Set(["2014", "2024"]);
const linter = new Linter();
/** @type {GlobalsSets | null} */
let cachedGlobals = null;

/** @returns {GlobalsSets} */
export function loadGlobals() {
	if (!cachedGlobals) {
		let raw;
		try {
			raw = readFileSync(GENERATED, "utf8");
		} catch {
			// ! Loud, never a silent fallback to a smaller whitelist (the settings.json lesson)
			throw new Error("globals.generated.json missing - run `pnpm run analyze` first");
		}
		cachedGlobals = JSON.parse(raw);
	}
	return /** @type {GlobalsSets} */ (cachedGlobals);
}

/**
 * @param {string} source
 * @param {string} edition
 * @param {GlobalsSets} [globalsData]
 * @returns {{ findings: Finding[], notes: string[] }}
 */
export function lint(source, edition, globalsData = loadGlobals()) {
	/** @type {string[]} */
	const notes = [];
	let resolved = edition;
	if (!EDITIONS.has(resolved)) {
		notes.push(`unknown edition "${edition}" - validated against the 2014 rule set`);
		resolved = "2014";
	}
	const config = buildConfig(/** @type {import("./generate-globals.mjs").Edition} */ (resolved), globalsData);
	const messages = linter.verify(source, config);
	const findings = messages.map((m) => ({
		line: m.line ?? 0,
		column: m.column ?? 0,
		ruleId: m.ruleId ?? (m.fatal ? "parse-error" : "unknown"),
		severity: m.severity === 2 ? /** @type {const} */ ("error") : /** @type {const} */ ("warning"),
		message: m.message,
	}));
	return { findings, notes };
}

import { describe, expect, it } from "vitest";
import { buildGlobals } from "../src/generate-globals.mjs";

const NO_OVERRIDES = { common: {}, 2014: {}, 2024: {} };

function report(extra = {}) {
	return {
		engine_surface_by_repo: {
			mpmb_source: { registries: ["SpellsList"], functions: ["What"] },
			mpmb_source_2024: { registries: ["SpellsList", "DefaultEvalsList"], functions: ["What"] },
		},
		implicit_globals: [],
		undeclared_by_repo: {},
		...extra,
	};
}

describe("buildGlobals", () => {
	it("buckets names shared by both engine repos into common", () => {
		const out = buildGlobals(report(), NO_OVERRIDES);
		expect(out.common).toEqual(["SpellsList", "What"]);
		expect(out["2014"]).toEqual([]);
		expect(out["2024"]).toEqual(["DefaultEvalsList"]);
	});

	it("maps implicit globals through their repo's edition", () => {
		const out = buildGlobals(report({ implicit_globals: [{ repo: "mpmb_source", name: "CurrentStats", classification: "host-write" }] }), NO_OVERRIDES);
		expect(out["2014"]).toContain("CurrentStats");
	});

	it("trusts undeclared names from engine repos but not imports", () => {
		const out = buildGlobals(report({ undeclared_by_repo: { mpmb_source: ["tDoc"], imports_source: ["SomeTypo"] } }), NO_OVERRIDES);
		expect(out["2014"]).toContain("tDoc");
		expect(JSON.stringify(out)).not.toContain("SomeTypo");
	});

	it("applies overrides last", () => {
		const out = buildGlobals(report(), {
			common: { add: ["ManuallyBlessed"] },
			2014: {},
			2024: { remove: ["DefaultEvalsList"] },
		});
		expect(out.common).toContain("ManuallyBlessed");
		expect(out["2024"]).not.toContain("DefaultEvalsList");
	});

	it("fails loudly when the report predates the per-repo surface", () => {
		expect(() => buildGlobals({ implicit_globals: [] }, NO_OVERRIDES)).toThrow(/engine_surface_by_repo/);
	});
});

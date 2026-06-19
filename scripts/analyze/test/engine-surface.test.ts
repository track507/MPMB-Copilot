import { describe, it, expect } from "vitest";
import { buildEngineSurface } from "../src/engine-surface";

describe("buildEngineSurface", () => {
	it("discovers registries, every function, and derived Add* (no hardcoded list)", () => {
		const engine = [
			"var SpellsList = SpellsList || {};",
			"var classes = {};",
			"function AddSubClass(c, s){ return c; }",
			"function CreateSpellList(o){ return o; }",
			"var helper = function(a, b){ return a; };",
		];
		const surface = buildEngineSurface(engine);

		expect(surface.registries.has("SpellsList")).toBe(true);
		expect(surface.registries.has("classes")).toBe(true);
		expect(surface.functions.get("CreateSpellList")).toMatchObject({ arity: 1, kind: "declaration" });
		expect(surface.functions.get("helper")).toMatchObject({ arity: 2, kind: "var_function" });
		expect([...surface.addDeclarations]).toContain("AddSubClass");
		expect([...surface.addDeclarations]).not.toContain("CreateSpellList");
	});
});

import { describe, it, expect } from "vitest";
import { diffCatalogs } from "../src/migrate-diff";

describe("diffCatalogs", () => {
	it("reports missing-in-new and new-only per collection", () => {
		const oldCat = {
			objects: [{ repo: "imports_source", file: "a.js", object_type: "SpellsList", object_key: "x" }],
			add_calls: [],
			functions: [],
		};
		const newCat = {
			objects: [
				{ repo: "imports_source", file: "a.js", object_type: "SpellsList", object_key: "x" },
				{ repo: "imports_source", file: "a.js", object_type: "RaceList", object_key: "y" },
			],
			add_calls: [],
			functions: [],
		};
		const d = diffCatalogs(oldCat, newCat);
		expect(d.missingInNew.objects).toEqual([]);
		expect(d.newOnly.objects).toHaveLength(1);
	});
});

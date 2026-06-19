import { describe, it, expect } from "vitest";
import { buildEngineSurface } from "../src/engine-surface";
import { extractFile } from "../src/extract";
import { buildReport } from "../src/report";

describe("buildReport", () => {
	it("emits the CatalogModel v1 contract plus additive sections", () => {
		const surface = buildEngineSurface(["var SpellsList = {}; function AddSubClass(){}"]);
		const perFile = [
			extractFile('SpellsList["x"] = {}; AddSubClass(); LeakyThing = {};', {
				repo: "imports_source",
				file: "a.js",
				edition: "2014",
			}),
		];
		const report = buildReport({
			repos: {
				imports_source: { branch: "main", commit: "abc", short_commit: "abc", date: "x", subject: "x", refs: "", remote: "" },
			},
			perFile,
			surface,
			hostSet: new Set(),
			generatedAt: "2026-06-18T00:00:00.000Z",
		});

		for (const k of [
			"generated_at",
			"project_root",
			"repos",
			"objects",
			"add_calls",
			"functions",
			"coverage_metrics",
			"source_keys",
			"required_versions",
		]) {
			expect(report).toHaveProperty(k);
		}
		expect(report.objects[0]).toMatchObject({ object_type: "SpellsList", assignment_kind: "bracket_object" });
		expect(report.add_calls.find((c) => c.function_name === "AddSubClass")?.mapped).toBe(true);
		expect(report.add_calls.find((c) => c.function_name === "AddSubClass")?.end_line).toEqual(expect.any(Number));
		expect(report.implicit_globals.find((g) => g.name === "LeakyThing")?.classification).toBe("leak-candidate");
		expect(report.undeclared_seed).toEqual(expect.arrayContaining(["LeakyThing"]));
	});
});

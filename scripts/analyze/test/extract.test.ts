import { describe, it, expect } from "vitest";
import { extractFile } from "../src/extract";

const at = (repo = "imports_source", file = "x.js", edition = "2014") => ({ repo, file, edition });

describe("extractFile", () => {
	it("classifies registry write kinds incl. dot and nested", () => {
		const code = [
			'SpellsList["fireball"] = { name: "Fireball" };',
			'SourceList.P = { name: "PHB" };',
			'MagicItemsList["ring"] = function () { return 1; };',
			"classes.primary = { name: 1 };",
		].join("\n");
		const { objects } = extractFile(code, at());
		const byType = Object.fromEntries(objects.map((o) => [o.object_type, o]));
		expect(byType.SpellsList).toMatchObject({ object_key: "fireball", assignment_kind: "bracket_object" });
		expect(byType.SourceList).toMatchObject({ object_key: "P", assignment_kind: "dot_object" });
		expect(byType.MagicItemsList).toMatchObject({ assignment_kind: "function_object" });
		expect(byType.classes).toMatchObject({ object_key: "primary", assignment_kind: "dot_object" });
		expect(byType.SpellsList.end_line).toBeGreaterThanOrEqual(byType.SpellsList.line);
	});

	it("captures function kinds", () => {
		const { functions } = extractFile("function f(){} var g = function(a){};", at());
		expect(functions).toEqual(
			expect.arrayContaining([expect.objectContaining({ name: "f", kind: "declaration" }), expect.objectContaining({ name: "g", kind: "var_function" })])
		);
	});

	it("flags implicit globals (bare assignment) but not declared vars", () => {
		const r = extractFile("var local = {}; ChangesDialogSkip = { chXP: true };", at());
		expect(r.implicitGlobals.map((g) => g.name)).toContain("ChangesDialogSkip");
		expect(r.implicitGlobals.map((g) => g.name)).not.toContain("local");
	});

	it("records call sites and undeclared reads", () => {
		const r = extractFile('RequiredSheetVersion("13.1.9"); Value("x", 1);', at());
		expect(r.calls.map((c) => c.callee)).toEqual(expect.arrayContaining(["RequiredSheetVersion", "Value"]));
		expect(r.unresolved.map((u) => u.name)).toEqual(expect.arrayContaining(["RequiredSheetVersion", "Value"]));
	});
});

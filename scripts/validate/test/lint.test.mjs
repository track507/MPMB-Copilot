import { describe, expect, it } from "vitest";
import { lint } from "../src/lint.mjs";

/** @type {import("../src/generate-globals.mjs").GlobalsSets} */
const GLOBALS = { common: ["SpellsList", "RequiredSheetVersion"], 2014: [], 2024: ["DefaultEvalsList"] };

/**
 * @param {string} source
 * @param {string} [edition]
 */
function errorsOf(source, edition = "2014") {
	return lint(source, edition, GLOBALS).findings.filter((f) => f.severity === "error");
}

describe("ES6 bans carry teaching messages", () => {
	/** @type {[string, RegExp][]} */
	const cases = [
		["let x = 1;", /let is not available/],
		["const x = 1;", /const is not available/],
		["var f = () => 1;", /Arrow functions/],
		["var s = `hi`;", /Template literals/],
		["for (var x of []) {}", /for\.\.\.of/],
		["var a = [1].concat([2, 3]); var b = [0, ...a];", /spread/i],
		["function f(a) { var { b } = a; return b; }", /Destructuring/],
		["function f(a = 1) { return a; }", /Default parameters/],
		["var p = {}.a?.b;", /Optional chaining/],
		["var x = null ?? 1;", /Nullish/],
		["var y = 2 ** 3;", /Math\.pow/],
		["async function f() {}", /async\/await/],
		["function* g() {}", /Generators/],
		["var o = { m() {} };", /Method shorthand/],
		["var r = /x/u;", /Regex flags/],
	];
	for (const [source, pattern] of cases) {
		it(`flags: ${source}`, () => {
			const errors = errorsOf(source);
			expect(errors.length).toBeGreaterThan(0);
			expect(errors.map((f) => f.message).join("\n")).toMatch(pattern);
		});
	}
});

describe("AcroJS console rules", () => {
	it("flags console.log with the println teaching message", () => {
		expect(
			errorsOf('console.log("hi");')
				.map((f) => f.message)
				.join("\n")
		).toMatch(/console\.println/);
	});
	it("accepts console.println", () => {
		expect(errorsOf('console.println("hi");')).toEqual([]);
	});
});

describe("edition-aware globals", () => {
	it("accepts a known registry write", () => {
		expect(errorsOf('SpellsList["fire bolt"] = { name : "Fire Bolt" };')).toEqual([]);
	});
	it("flags an unknown global", () => {
		expect(errorsOf("MadeUpList.x = 1;").map((f) => f.ruleId)).toContain("no-undef");
	});
	it("scopes DefaultEvalsList to 2024", () => {
		const source = 'DefaultEvalsList["x"] = 1;';
		expect(errorsOf(source, "2024")).toEqual([]);
		expect(errorsOf(source, "2014").map((f) => f.ruleId)).toContain("no-undef");
	});
});

describe("MPMB file conventions", () => {
	it("exempts iFileName from no-unused-vars", () => {
		expect(lint('var iFileName = "file.js";', "2014", GLOBALS).findings).toEqual([]);
	});
	it("still warns on other unused vars", () => {
		expect(lint("var unusedThing = 1;", "2014", GLOBALS).findings.map((f) => f.ruleId)).toContain("no-unused-vars");
	});
});

describe("degraded inputs", () => {
	it("returns a parse error as a single finding, not a crash", () => {
		const { findings } = lint("function {", "2014", GLOBALS);
		expect(findings).toHaveLength(1);
		expect(findings[0].ruleId).toBe("parse-error");
		expect(findings[0].severity).toBe("error");
	});
	it("falls back to 2014 with a note on unknown editions", () => {
		const { findings, notes } = lint("var x = 1; console.println(x);", "3024", GLOBALS);
		expect(notes[0]).toMatch(/unknown edition/);
		expect(findings.filter((f) => f.severity === "error")).toEqual([]);
	});
});

describe("quality rules stay warnings", () => {
	it("warns (not errors) on == and eval", () => {
		const { findings } = lint('var x = 1; if (x == "1") { eval("x"); }', "2014", GLOBALS);
		expect(findings.map((f) => f.ruleId)).toEqual(expect.arrayContaining(["eqeqeq", "no-eval"]));
		expect(findings.some((f) => f.severity === "error")).toBe(false);
	});
});

describe("corpus-driven severities", () => {
	it("does not flag the field re-render idiom (property self-assign)", () => {
		expect(lint("var o = { a : 1 }; o.a = o.a;", "2014", GLOBALS).findings).toEqual([]);
	});
	it("keeps plain self-assignment a warning", () => {
		const { findings } = lint("var x = 1; x = x; console.println(x);", "2014", GLOBALS);
		expect(findings.map((f) => [f.ruleId, f.severity])).toEqual([["no-self-assign", "warning"]]);
	});
	it("keeps redeclaration and fallthrough warnings, not errors", () => {
		const { findings } = lint("var x = 1; var x = 2; switch (x) { case 1: x++; case 2: break; }", "2014", GLOBALS);
		expect(findings.length).toBeGreaterThan(0);
		expect(findings.some((f) => f.severity === "error")).toBe(false);
		expect(findings.map((f) => f.ruleId)).toEqual(expect.arrayContaining(["no-redeclare", "no-fallthrough"]));
	});
});

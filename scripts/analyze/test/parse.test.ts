import { describe, it, expect } from "vitest";
import { parseFile } from "../src/parse";

describe("parseFile", () => {
	it("parses AcroJS and builds a global scope", () => {
		const r = parseFile("var x = 1; function f(){ return this; }");
		expect(r.parseError).toBeNull();
		expect(r.ast?.type).toBe("Program");
		expect(r.scopeManager?.globalScope).toBeTruthy();
	});

	it("allows top-level return (globalReturn)", () => {
		expect(parseFile("if (true) { return; }").parseError).toBeNull();
	});

	it("builds scope for functions with parameters (eslint-scope needs node ranges)", () => {
		const r = parseFile("function f(a, b){ return a; }");
		expect(r.parseError).toBeNull();
		expect(r.scopeManager?.globalScope).toBeTruthy();
	});

	it("records a parse error instead of throwing", () => {
		const r = parseFile("function ( {");
		expect(r.ast).toBeNull();
		expect(r.parseError?.message).toEqual(expect.any(String));
	});
});

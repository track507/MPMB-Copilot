import { describe, it, expect } from "vitest";
import { classifyImplicit, classifyName } from "../src/classify";
import type { EngineSurface } from "../src/types";

const surface: EngineSurface = {
	registries: new Set(["SpellsList"]),
	functions: new Map([["CreateSpellList", { arity: 1, kind: "declaration" }]]),
	addDeclarations: new Set(),
};

describe("classify", () => {
	it("resolves names against the engine surface then host set", () => {
		expect(classifyName("CreateSpellList", surface, new Set())).toBe("engine-fn");
		expect(classifyName("SpellsList", surface, new Set())).toBe("registry");
		expect(classifyName("Value", surface, new Set(["Value"]))).toBe("host-API");
		expect(classifyName("Value", surface, new Set())).toBe("undeclared");
	});

	it("splits implicit globals into host-write vs leak-candidate", () => {
		expect(classifyImplicit("ChangesDialogSkip", surface, new Set(["ChangesDialogSkip"]))).toBe("host-write");
		expect(classifyImplicit("ChangesDialogSkip", surface, new Set())).toBe("leak-candidate");
	});
});

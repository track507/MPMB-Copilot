import { describe, expect, it } from "vitest";
import { serializeSurfaces } from "../src/report";
import type { EngineSurface } from "../src/types";

function surface(registries: string[], functions: string[]): EngineSurface {
	return {
		registries: new Set(registries),
		functions: new Map(functions.map((n) => [n, { arity: 0, kind: "declaration" as const }])),
		addDeclarations: new Set(),
	};
}

describe("serializeSurfaces", () => {
	it("emits sorted name arrays per repo", () => {
		const out = serializeSurfaces({
			mpmb_source: surface(["SpellsList", "ClassList"], ["What"]),
			mpmb_source_2024: surface(["DefaultEvalsList"], []),
		});
		expect(out.mpmb_source).toEqual({ registries: ["ClassList", "SpellsList"], functions: ["What"] });
		expect(out.mpmb_source_2024).toEqual({ registries: ["DefaultEvalsList"], functions: [] });
	});
});

import type { EngineSurface, ImplicitClass, ReferenceClass } from "./types";

export function classifyName(name: string, surface: EngineSurface, hostSet: Set<string>): ReferenceClass {
	if (surface.functions.has(name)) return "engine-fn";
	if (surface.registries.has(name)) return "registry";
	if (hostSet.has(name)) return "host-API";
	return "undeclared";
}

export function classifyImplicit(name: string, surface: EngineSurface, hostSet: Set<string>): ImplicitClass {
	// ? a write to a known host/registry symbol is intentional; otherwise it is a candidate leak
	if (surface.registries.has(name) || surface.functions.has(name) || hostSet.has(name)) return "host-write";
	return "leak-candidate";
}

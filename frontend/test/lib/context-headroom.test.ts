import { describe, expect, it } from "vitest";
import { contextHeadroom, formatHeadroom, HEADROOM_REVEAL_AT, selectedContextWindow } from "@/lib/context-headroom";
import type { CapabilityEnvelope } from "@/types/settings";

// ! Cast rather than a full envelope: CapabilityEnvelope declares six capabilities and these functions read one
const envelope = (
	provider: string,
	model: string,
	entries: Record<string, ReadonlyArray<{ id: string; context_window?: number | null }>>
): CapabilityEnvelope => ({ generation: { current: { provider, model, effort: "high" }, entries } }) as unknown as CapabilityEnvelope;

describe("selectedContextWindow", () => {
	it("reads the window off the entry for the selected provider and model", () => {
		const caps = envelope("anthropic", "claude-sonnet-4-6", {
			anthropic: [{ id: "claude-sonnet-4-6", context_window: 1_000_000 }],
		});
		expect(selectedContextWindow(caps)).toBe(1_000_000);
	});

	it("does not match a same-named model under another provider", () => {
		// ? The catalog is keyed by provider, so a model id alone is ambiguous
		const caps = envelope("openai", "shared-id", {
			anthropic: [{ id: "shared-id", context_window: 200_000 }],
			openai: [{ id: "other", context_window: 400_000 }],
		});
		expect(selectedContextWindow(caps)).toBeNull();
	});

	it("returns null for a model the catalog does not list", () => {
		// ? An Ollama or free-form model is legitimately absent
		expect(selectedContextWindow(envelope("ollama", "llama3", { ollama: [] }))).toBeNull();
	});

	it("returns null when the entry records no window", () => {
		const caps = envelope("anthropic", "m", { anthropic: [{ id: "m", context_window: null }] });
		expect(selectedContextWindow(caps)).toBeNull();
	});

	it("returns null before the capabilities query resolves", () => {
		expect(selectedContextWindow(undefined)).toBeNull();
	});
});

describe("contextHeadroom", () => {
	it("stays hidden below the reveal threshold", () => {
		// ! Returning null rather than a low fraction keeps the threshold in one place
		expect(contextHeadroom(1_000, 1_000_000)).toBeNull();
	});

	it("appears at the reveal threshold", () => {
		const at = Math.ceil(1_000_000 * HEADROOM_REVEAL_AT);
		expect(contextHeadroom(at, 1_000_000)).not.toBeNull();
	});

	it("clamps a window the model has already exceeded", () => {
		// ! Price data can lag a limit change, and a bar past 100% reads as a rendering bug
		expect(contextHeadroom(250_000, 200_000)?.fraction).toBe(1);
	});

	it("returns null when no window is known", () => {
		expect(contextHeadroom(900_000, null)).toBeNull();
	});

	it("returns null before any turn has reported usage", () => {
		expect(contextHeadroom(undefined, 1_000_000)).toBeNull();
		expect(contextHeadroom(0, 1_000_000)).toBeNull();
	});
});

describe("formatHeadroom", () => {
	// Given its own input rather than contextHeadroom's output, so the two are tested independently
	it("floors the percentage so a near-full context never reads as full", () => {
		expect(formatHeadroom({ used: 199_200, window: 200_000, fraction: 0.996 })).toBe("99% of context");
	});

	it("reads as a fraction of context rather than a bare number", () => {
		expect(formatHeadroom({ used: 150_000, window: 200_000, fraction: 0.75 })).toBe("75% of context");
	});

	it("reports a clamped context as full", () => {
		expect(formatHeadroom({ used: 250_000, window: 200_000, fraction: 1 })).toBe("100% of context");
	});
});

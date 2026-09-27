import type { CapabilityEnvelope, ModelOption } from "@/types/settings";

/**
 * How full the model's context was on the last turn
 */
export interface ContextHeadroom {
	readonly used: number;
	readonly window: number;
	readonly fraction: number;
}

export const HEADROOM_REVEAL_AT = 0.6;

/**
 * The selected model's context window, or null when nothing knows it
 */
export function selectedContextWindow(capabilities: CapabilityEnvelope | undefined): number | null {
	const generation = capabilities?.generation;
	if (generation === undefined) return null;

	const { provider, model } = generation.current;
	const entries: readonly ModelOption[] | undefined =
		provider === "anthropic" || provider === "openai" || provider === "ollama" ? generation.entries[provider] : undefined;
	const window = entries?.find((entry) => entry.id === model)?.context_window;
	return window === undefined || window === null || window <= 0 ? null : window;
}

/**
 * Headroom for the last turn, or null when it cannot be computed or is not worth showing
 */
export function contextHeadroom(inputTokens: number | undefined, window: number | null): ContextHeadroom | null {
	if (inputTokens === undefined || inputTokens <= 0 || window === null) return null;

	const fraction = inputTokens / window;
	if (fraction < HEADROOM_REVEAL_AT) return null;
	return { used: inputTokens, window, fraction: Math.min(fraction, 1) };
}

/**
 * A percentage for display, floored so 99.6% never reads as a full context
 */
export function formatHeadroom(headroom: ContextHeadroom): string {
	return `${String(Math.floor(headroom.fraction * 100))}% of context`;
}

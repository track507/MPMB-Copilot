import type { Message } from "@/types/session";

const TURN_COST = new Intl.NumberFormat(undefined, {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 4,
});

const SESSION_COST = new Intl.NumberFormat(undefined, {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 2,
});

const MESSAGE_LIMIT = 100;

/** One turn's cost, or null when the model could not be priced */
export function formatTurnCost(costUsd: string | null | undefined): string | null {
	if (costUsd === undefined || costUsd === null) return null;
	if (costUsd.trim() === "" || !Number.isFinite(Number(costUsd))) return null;
	return TURN_COST.format(costUsd as Intl.StringNumericLiteral);
}

export interface SessionCost {
	readonly usd: number;
	readonly unpriced: number;
	readonly truncated: boolean;
}

/**
 * Sum a session's spend from messages already in hand
 */
export function sessionCost(messages: readonly Message[]): SessionCost {
	let usd = 0;
	let unpriced = 0;
	for (const message of messages) {
		if (message.role !== "assistant") continue;
		const cost = message.meta_data.usage?.cost_usd;
		// null means the model could not be priced; undefined means no usage was recorded at all
		if (cost === undefined || cost === null) {
			unpriced += 1;
			continue;
		}
		usd += Number(cost);
	}
	return { usd, unpriced, truncated: messages.length >= MESSAGE_LIMIT };
}

/**
 * A session total, prefixed when it is provably incomplete
 */
export function formatSessionTotal(cost: SessionCost): string {
	const formatted = SESSION_COST.format(cost.usd);
	return cost.unpriced > 0 || cost.truncated ? `at least ${formatted}` : formatted;
}

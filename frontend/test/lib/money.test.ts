import { describe, expect, it } from "vitest";
import { formatSessionTotal, formatTurnCost, sessionCost } from "@/lib/money";
import type { Message } from "@/types/session";

const assistant = (costUsd: string | null | undefined): Message => ({ role: "assistant", meta_data: { usage: { cost_usd: costUsd } } }) as unknown as Message;

const user = (): Message => ({ role: "user", meta_data: {} }) as unknown as Message;

describe("formatTurnCost", () => {
	it("renders four fraction digits so a sub-cent cost is not shown as zero", () => {
		expect(formatTurnCost("0.0043")).toBe("$0.0043");
	});

	it("keeps two digits on a round value so it still reads as money", () => {
		expect(formatTurnCost("1.5")).toBe("$1.50");
	});

	it("returns null for an unpriced turn rather than a zero", () => {
		expect(formatTurnCost(null)).toBeNull();
		expect(formatTurnCost(undefined)).toBeNull();
	});

	it("returns null for a malformed value instead of $0.00 or $NaN", () => {
		expect(formatTurnCost("")).toBeNull();
		expect(formatTurnCost("   ")).toBeNull();
		expect(formatTurnCost("abc")).toBeNull();
	});

	it("formats the string exactly, without a float round trip", () => {
		expect(formatTurnCost("0.00005")).toBe("$0.0001");
	});
});

describe("sessionCost", () => {
	it("sums only assistant turns", () => {
		expect(sessionCost([assistant("0.01"), user(), assistant("0.02")]).usd).toBeCloseTo(0.03);
	});

	it("does not count a user turn as unpriced", () => {
		expect(sessionCost([user(), assistant("0.01")]).unpriced).toBe(0);
	});

	it("counts an unpriced assistant turn", () => {
		const cost = sessionCost([assistant("0.01"), assistant(null)]);
		expect(cost.unpriced).toBe(1);
		expect(cost.usd).toBeCloseTo(0.01);
	});

	it("counts an assistant turn with no usage recorded at all", () => {
		expect(sessionCost([assistant(undefined)]).unpriced).toBe(1);
	});

	it("reports an empty session as zero rather than unknown", () => {
		expect(sessionCost([])).toEqual({ usd: 0, unpriced: 0, truncated: false });
	});

	it("flags truncation at the loader's message limit", () => {
		const many = Array.from({ length: 100 }, () => assistant("0"));
		expect(sessionCost(many).truncated).toBe(true);
		expect(sessionCost(many.slice(0, 99)).truncated).toBe(false);
	});
});

describe("formatSessionTotal", () => {
	it("reports an exact total when every turn was priced", () => {
		expect(formatSessionTotal(sessionCost([assistant("0.01")]))).toBe("$0.01");
	});

	it("prefixes with at least when a turn could not be priced", () => {
		expect(formatSessionTotal(sessionCost([assistant("0.01"), assistant(null)]))).toBe("at least $0.01");
	});

	it("prefixes with at least when the message list was truncated", () => {
		expect(formatSessionTotal(sessionCost(Array.from({ length: 100 }, () => assistant("0.01"))))).toMatch(/^at least /);
	});

	it("does not inflate a float sum the way roundingMode ceil would", () => {
		expect(formatSessionTotal(sessionCost([assistant("0.1"), assistant("0.2")]))).toBe("$0.30");
	});
});

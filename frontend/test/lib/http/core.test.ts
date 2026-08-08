import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "@/lib/http";

describe("toApiError", () => {
	it("maps a problem body to ApiError with detail as the message", () => {
		const err = toApiError(413, {
			type: "/api/problems/file-too-large",
			title: "File too large",
			status: 413,
			detail: "Too big.",
		});
		expect(err).toBeInstanceOf(ApiError);
		expect(err.status).toBe(413);
		expect(err.message).toBe("Too big.");
		expect(err.problem?.type).toBe("/api/problems/file-too-large");
	});

	it("tolerates a non-problem body (problem is null, message falls back)", () => {
		const err = toApiError(500, "not json-ish");
		expect(err.problem).toBeNull();
		expect(err.status).toBe(500);
		expect(err.message).toContain("500");
	});
});

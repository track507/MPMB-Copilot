import { expect, it, vi } from "vitest";
import { ApiError } from "@/lib/http/core";
import { streamChat } from "@/lib/http/chat-stream";

it("throws ApiError when the opening response is not ok", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn().mockResolvedValue(
			new Response(JSON.stringify({ type: "about:blank", title: "Unauthorized", status: 401, detail: "No." }), {
				status: 401,
			}),
		)
	);
	await expect(streamChat({ message: "hi" }, vi.fn())).rejects.toBeInstanceOf(ApiError);
	vi.unstubAllGlobals();
});

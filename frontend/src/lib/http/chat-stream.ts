import type { ChatRequest, ChatStreamChunk } from "@/types/chat";

import { BASE_URL, toApiError } from "./core";

/**
 * POST a chat turn and stream the SSE reply
 *
 * Transport only: parses `data:` frames into ChatStreamChunk and hands each to onChunk
 * The caller (use-chat) owns React state, navigation, and the store
 * A non-2xx opening response is surfaced as an ApiError; failures that arrive mid-stream come through as chunks and stay the caller's concern
 */
export async function streamChat(body: ChatRequest, onChunk: (chunk: ChatStreamChunk) => void, signal?: AbortSignal): Promise<void> {
	const response = await fetch(`${BASE_URL}/api/chat/stream`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
		signal: signal ?? null,
	});

	if (!response.ok) {
		const errBody: unknown = await response.json().catch(() => null);
		throw toApiError(response.status, errBody);
	}

	const reader = response.body?.getReader();
	if (reader === undefined) {
		throw new Error("No response body");
	}

	const decoder = new TextDecoder();
	let buffer = "";

	for (;;) {
		const { done, value } = await reader.read();
		if (done) break;

		buffer += decoder.decode(value, { stream: true });

		// Parse SSE events from the buffer; keep the trailing partial line.
		const lines = buffer.split("\n");
		buffer = lines.pop() ?? "";

		for (const line of lines) {
			if (!line.startsWith("data: ")) continue;
			const data = line.slice(6).trim();
			if (data === "[DONE]") continue;
			try {
				onChunk(JSON.parse(data) as ChatStreamChunk);
			} catch {
				// Skip malformed chunks
			}
		}
	}
}

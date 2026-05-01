import { useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useChatStore } from "@/stores/chat-store";
import type { ChatRequest, ChatStreamChunk } from "@/types/chat";

interface UseChatOptions {
	readonly sessionId: string | null;
	readonly onError?: (error: Error) => void;
}

interface UseChatReturn {
	readonly sendMessage: (message: string, overrides?: Partial<ChatRequest>) => void;
	readonly cancelStream: () => void;
}

export function useChat({ sessionId, onError }: UseChatOptions): UseChatReturn {
	const abortRef = useRef<AbortController | null>(null);
	const queryClient = useQueryClient();
	const [, setSearchParams] = useSearchParams();

	// Abort any in-flight stream when the hook unmounts (e.g. session switch remounts ChatWindow)
	useEffect(() => {
		return () => {
			if (abortRef.current !== null) {
				abortRef.current.abort();
				abortRef.current = null;
			}
			useChatStore.getState().reset();
		};
	}, []);

	const cancelStream = useCallback(() => {
		if (abortRef.current !== null) {
			abortRef.current.abort();
			abortRef.current = null;
		}
		useChatStore.getState().reset();
	}, []);

	const sendMessage = useCallback(
		(message: string, overrides?: Partial<ChatRequest>) => {
			// Cancel any existing stream
			if (abortRef.current !== null) {
				abortRef.current.abort();
			}

			const controller = new AbortController();
			abortRef.current = controller;

			const body: ChatRequest = {
				message,
				session_id: sessionId ?? undefined,
				include_source: true,
				...overrides,
			};

			const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

			void (async (): Promise<void> => {
				try {
					const response = await fetch(`${baseUrl}/api/chat/stream`, {
						method: "POST",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify(body),
						signal: controller.signal,
					});

					if (!response.ok) {
						throw new Error(`Chat request failed: ${String(response.status)}`);
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

						// Parse SSE events from buffer
						const lines = buffer.split("\n");
						buffer = lines.pop() ?? "";

						for (const line of lines) {
							if (line.startsWith("data: ")) {
								const data = line.slice(6).trim();
								if (data === "[DONE]") continue;

								try {
									const chunk = JSON.parse(data) as ChatStreamChunk;
									if (chunk.done) {
										useChatStore.getState().completeStream(chunk.metadata ?? null);
										const newSessionId = chunk.metadata?.session_id;
										// Navigate to new session if created, but only if we didn't already have a session (i.e. this was the first message in a new conversation)
										if (sessionId === null && newSessionId !== undefined && newSessionId !== "") {
											setSearchParams(
												(prev) => {
													const next = new URLSearchParams(prev);
													next.set("session", newSessionId);
													return next;
												},
												{ replace: true }
											);
										}
									} else if (chunk.event === "tool_start" && chunk.tool) {
										useChatStore.getState().onToolStart(chunk.tool);
									} else if (chunk.event === "tool_end" && chunk.tool) {
										useChatStore.getState().onToolEnd(chunk.tool);
									} else if (chunk.chunk) {
										useChatStore.getState().appendStreamChunk(chunk.chunk);
									}
								} catch {
									// Skip malformed chunks
								}
							}
						}
					}

					// Refresh session data after complete response
					await queryClient.invalidateQueries({ queryKey: ["sessions"] });

					// Server has caught up - clear optimistic UI but keep metadata for footer
					useChatStore.getState().clearOptimistic();
				} catch (err: unknown) {
					if (err instanceof DOMException && err.name === "AbortError") return;
					const error = err instanceof Error ? err : new Error(String(err));
					onError?.(error);
					useChatStore.getState().reset();
				} finally {
					abortRef.current = null;
				}
			})();
		},
		[sessionId, onError, queryClient, setSearchParams]
	);

	return { sendMessage, cancelStream };
}

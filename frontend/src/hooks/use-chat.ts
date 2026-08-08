import { useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { streamChat } from "@/lib/http";
import { useChatStore } from "@/stores/chat-store";
import type { ChatRequest, ChatStreamChunk } from "@/types/chat";
import type { SessionDetail } from "@/types/session";

interface UseChatOptions {
	readonly sessionId: string | null;
	readonly onError?: (error: Error) => void;
}

interface UseChatReturn {
	readonly sendMessage: (message: string, overrides?: Partial<ChatRequest>) => void;
	readonly cancelStream: () => void;
}

/**
 * Seed the session-detail query cache with the just-finished exchange so the post-create route change renders instantly
 * The subsequent invalidate refetch replaces this with server-authoritative data (real ids, generated title)
 */
function primeSessionDetail(queryClient: ReturnType<typeof useQueryClient>, sessionId: string, userText: string, metadata: ChatStreamChunk["metadata"]): void {
	const now = Temporal.Now.instant().toString();
	const optimistic: SessionDetail = {
		id: sessionId,
		title: "New Conversation",
		created_at: now,
		updated_at: now,
		user_id: null,
		settings: {},
		meta_data: {},
		message_count: 2,
		messages: [
			{
				id: `optimistic-user-${sessionId}`,
				session_id: sessionId,
				role: "user",
				content: { text: userText },
				created_at: now,
				sequence_number: 1,
				provider: null,
				model: null,
				prompt_tokens: 0,
				completion_tokens: 0,
				total_tokens: 0,
				latency_ms: null,
				stop_reason: null,
				meta_data: {},
				feedback: null,
			},
			{
				id: `optimistic-assistant-${sessionId}`,
				session_id: sessionId,
				role: "assistant",
				content: { text: useChatStore.getState().streamedText },
				created_at: now,
				sequence_number: 2,
				provider: metadata?.provider ?? null,
				model: metadata?.model ?? null,
				prompt_tokens: 0,
				completion_tokens: 0,
				total_tokens: 0,
				latency_ms: null,
				stop_reason: null,
				meta_data: metadata?.tools ? { tools: metadata.tools } : {},
				feedback: null,
			},
		],
	};
	queryClient.setQueryData(["sessions", sessionId], optimistic);
}

export function useChat({ sessionId, onError }: UseChatOptions): UseChatReturn {
	const abortRef = useRef<AbortController | null>(null);
	const queryClient = useQueryClient();
	const navigate = useNavigate();

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

			void (async (): Promise<void> => {
				try {
					await streamChat(
						body,
						(chunk) => {
							if (chunk.done) {
								useChatStore.getState().completeStream(chunk.metadata ?? null);
								const newSessionId = chunk.metadata?.session_id;
								// First message in a new conversation: the backend just created the session, so adopt its id into the route (/chat/:id)
								if (sessionId === null && newSessionId !== undefined && newSessionId !== "") {
									// ? Prime the detail cache before navigating
									// ? The route change remounts ChatWindow (key flips new -> id), whose unmount resets the store
									// ? without this the streamed reply would flash empty until the refetch lands
									primeSessionDetail(queryClient, newSessionId, message, chunk.metadata);
									void navigate(`/chat/${newSessionId}`, { replace: true });
								}
							} else if (chunk.event === "tool_start" && chunk.tool) {
								useChatStore.getState().onToolStart(chunk.tool);
							} else if (chunk.event === "tool_end" && chunk.tool) {
								useChatStore.getState().onToolEnd(chunk.tool);
							} else if (chunk.chunk) {
								useChatStore.getState().appendStreamChunk(chunk.chunk);
							}
						},
						controller.signal
					);

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
		[sessionId, onError, queryClient, navigate]
	);

	return { sendMessage, cancelStream };
}

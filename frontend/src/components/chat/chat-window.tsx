import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Send, Square } from "lucide-react";
import { toast } from "sonner";
import { useParams } from "react-router";
import { useChat } from "@/hooks/use-chat";
import { useSession } from "@/hooks/use-sessions";
import { useSmoothText } from "@/hooks/use-smooth-text";
import { useChatStore } from "@/stores/chat-store";
import { MessageBubble } from "./message-bubble";
import { cn } from "@/lib/utils";
import type { KeyboardEventHandler, ReactElement, SubmitEventHandler } from "react";

// Per-tool status text shown in the streaming pill while a tool runs
const TOOL_PILL_TEXT: Record<string, string> = {
	mpmb_search: "Searching MPMB sources...",
	mpmb_read: "Reading source file...",
	mpmb_grep: "Searching for a pattern...",
	mpmb_function: "Looking up a function...",
};
const DEFAULT_PILL_TEXT = "Verifying code...";

export function ChatWindow(): ReactElement {
	const { sessionId: sessionIdParam } = useParams();
	const sessionId = sessionIdParam ?? null;

	const [input, setInput] = useState("");
	const messagesEndRef = useRef<HTMLDivElement>(null);
	const textareaRef = useRef<HTMLTextAreaElement>(null);

	const scrollContainerRef = useRef<HTMLDivElement>(null);
	const shouldAutoScrollRef = useRef(true);

	const { data: session } = useSession(sessionId);

	const handleError = useCallback((error: Error) => {
		toast.error(error.message);
	}, []);

	const { sendMessage, cancelStream } = useChat({
		sessionId,
		onError: handleError,
	});

	// Read transient state from the store
	const pendingUserMessage = useChatStore((s) => s.pendingUserMessage);
	const streamedText = useChatStore((s) => s.streamedText);
	const sawToolThisStream = useChatStore((s) => s.sawToolThisStream);
	const activeTool = useChatStore((s) => s.activeTool);
	const metadata = useChatStore((s) => s.metadata);
	const isStreaming = useChatStore((s) => s.isStreaming);

	// Reveal streamed text at a steady pace instead of in network-chunk bursts
	const smoothStreamedText = useSmoothText(streamedText);
	const isVisuallyStreaming = isStreaming || smoothStreamedText !== streamedText;

	// Server-confirmed messages from React Query
	const serverMessages = session?.messages ?? [];

	const showPendingUser = pendingUserMessage !== null && isStreaming;
	const showStreamedText = isStreaming || streamedText.length > 0;

	// Track whether user is near the bottom. Only auto-scroll when they are.
	const handleScroll = useCallback(() => {
		const container = scrollContainerRef.current;
		if (container === null) return;
		const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
		shouldAutoScrollRef.current = distanceFromBottom < 100;
	}, []);

	// Auto-scroll to bottom on new messages or streaming
	useEffect(() => {
		if (shouldAutoScrollRef.current) {
			messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
		}
	}, [serverMessages.length, smoothStreamedText, showPendingUser]);

	// Auto-resize textarea
	useEffect(() => {
		const textarea = textareaRef.current;
		if (textarea !== null) {
			textarea.style.height = "auto";
			textarea.style.height = `${String(Math.min(textarea.scrollHeight, 200))}px`;
		}
	}, [input]);

	const submitMessage = useCallback(() => {
		const trimmed = input.trim();
		if (trimmed.length === 0 || isStreaming) return;
		setInput("");
		shouldAutoScrollRef.current = true;

		// Optimistic: show user message immediately via the store
		useChatStore.getState().addUserMessage(trimmed);

		sendMessage(trimmed);
	}, [input, isStreaming, sendMessage]);

	const handleSubmit: SubmitEventHandler<HTMLFormElement> = useCallback(
		(e) => {
			e.preventDefault();
			submitMessage();
		},
		[submitMessage]
	);

	const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = useCallback(
		(e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				submitMessage();
			}
		},
		[submitMessage]
	);

	return (
		<div className="flex h-full min-w-0 flex-col">
			{/* Messages area */}
			<div ref={scrollContainerRef} onScroll={handleScroll} className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-6">
				<div className="mx-auto min-w-0 max-w-3xl space-y-6">
					{serverMessages.length === 0 && !isStreaming && pendingUserMessage === null && (
						<div className="py-24 text-center">
							<h2 className="text-2xl font-bold tracking-tight">MPMB Copilot</h2>
							<p className="mt-2 text-muted-foreground">Ask me about writing MPMB automation scripts for D&amp;D 5e character sheets.</p>
						</div>
					)}

					{serverMessages.map((msg) => (
						<MessageBubble
							key={msg.id}
							role={msg.role}
							content={msg.content.text}
							sources={msg.content.sources}
							tools={msg.meta_data.tools}
							cacheReadTokens={msg.meta_data.usage?.cache_read_tokens}
							stopReason={msg.stop_reason ?? undefined}
						/>
					))}

					{showPendingUser && <MessageBubble role="user" content={pendingUserMessage.text} />}

					{showStreamedText && (
						<MessageBubble
							role="assistant"
							content={smoothStreamedText}
							isStreaming={isVisuallyStreaming}
							tools={!isVisuallyStreaming ? metadata?.tools : undefined}
							cacheReadTokens={!isVisuallyStreaming ? metadata?.usage?.cache_read_tokens : undefined}
							stopReason={!isVisuallyStreaming ? metadata?.stop_reason : undefined}
						/>
					)}

					{isStreaming && sawToolThisStream && (
						<div className="mt-1 inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
							<Loader2 className="size-3.5 animate-spin" />
							<span>{(activeTool !== null ? TOOL_PILL_TEXT[activeTool] : undefined) ?? DEFAULT_PILL_TEXT}</span>
						</div>
					)}
					<div ref={messagesEndRef} />
				</div>
			</div>

			{/* Input area */}
			<div className="border-t border-border bg-background px-4 py-3">
				<form onSubmit={handleSubmit} className="mx-auto flex min-w-0 max-w-3xl items-end gap-2">
					<textarea
						ref={textareaRef}
						value={input}
						onChange={(e) => {
							setInput(e.target.value);
						}}
						onKeyDown={handleKeyDown}
						placeholder="Ask about MPMB scripting..."
						rows={1}
						className={cn(
							"flex-1 resize-none rounded-lg border border-input bg-background px-4 py-3",
							"text-sm placeholder:text-muted-foreground",
							"focus:outline-none focus:ring-2 focus:ring-ring"
						)}
					/>

					{isStreaming ? (
						<button
							type="button"
							onClick={cancelStream}
							className="shrink-0 rounded-lg bg-destructive p-3 text-destructive-foreground transition-colors hover:bg-destructive/90">
							<Square className="size-4" />
						</button>
					) : (
						<button
							type="submit"
							disabled={input.trim().length === 0}
							className="shrink-0 rounded-lg bg-primary p-3 text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
							<Send className="size-4" />
						</button>
					)}
				</form>
			</div>
		</div>
	);
}

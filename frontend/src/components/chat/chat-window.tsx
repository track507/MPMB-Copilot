import { useCallback, useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";
import { toast } from "sonner";
import { useSearchParams } from "react-router";
import { useChat } from "@/hooks/use-chat";
import { useSession } from "@/hooks/use-sessions";
import { useChatStore } from "@/stores/chat-store";
import { MessageBubble } from "./message-bubble";
import { cn } from "@/lib/utils";
import type { KeyboardEventHandler, ReactElement, SubmitEventHandler } from "react";

export function ChatWindow(): ReactElement {
	const [searchParams] = useSearchParams();
	const sessionId = searchParams.get("session");

	const [input, setInput] = useState("");
	const messagesEndRef = useRef<HTMLDivElement>(null);
	const textareaRef = useRef<HTMLTextAreaElement>(null);

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
	const isStreaming = useChatStore((s) => s.isStreaming);

	// Server-confirmed messages from React Query
	const serverMessages = session?.messages ?? [];

	// Derive: show pending user message only if server hasn't confirmed it yet
	const lastServerMessage = serverMessages[serverMessages.length - 1];
	const showPendingUser = pendingUserMessage !== null && lastServerMessage?.content.text !== pendingUserMessage.text;

	// Derive: show streaming bubble only if server hasn't confirmed the assistant response yet
	const showStreamedText = streamedText.length > 0 && lastServerMessage?.role !== "assistant";

	// Auto-scroll to bottom on new messages or streaming
	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
	}, [serverMessages.length, streamedText, showPendingUser]);

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
		<div className="flex h-full flex-col">
			{/* Messages area */}
			<div className="flex-1 overflow-y-auto px-4 py-6">
				<div className="mx-auto max-w-3xl space-y-6">
					{serverMessages.length === 0 && !isStreaming && pendingUserMessage === null && (
						<div className="py-24 text-center">
							<h2 className="text-2xl font-bold tracking-tight">MPMB Copilot</h2>
							<p className="mt-2 text-muted-foreground">Ask me about writing MPMB automation scripts for D&amp;D 5e character sheets.</p>
						</div>
					)}

					{/* Server-confirmed messages */}
					{serverMessages.map((msg) => (
						<MessageBubble key={msg.id} role={msg.role} content={msg.content.text} sources={msg.content.sources} />
					))}

					{/* Optimistic user message */}
					{showPendingUser && <MessageBubble role="user" content={pendingUserMessage.text} />}

					{/* Streaming assistant response */}
					{showStreamedText && <MessageBubble role="assistant" content={streamedText} isStreaming={isStreaming} />}

					<div ref={messagesEndRef} />
				</div>
			</div>

			{/* Input area */}
			<div className="border-t border-border bg-background px-4 py-3">
				<form onSubmit={handleSubmit} className="mx-auto flex max-w-3xl items-end gap-2">
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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Paperclip, Send, Square } from "lucide-react";
import { apiClient, uploadFile } from "@/lib/http";
import { useUploadStore, UPLOAD_EXTENSIONS } from "@/stores/upload-store";
import { AttachmentChips } from "./attachment-chips";
import type { FileOut } from "@/types/uploads";
import { toast } from "sonner";
import { useParams } from "react-router";
import { useChat } from "@/hooks/use-chat";
import { useSession } from "@/hooks/use-sessions";
import { useSessionFiles } from "@/lib/uploads";
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
	mpmb_validate: "Validating the script...",
};
const DEFAULT_PILL_TEXT = "Verifying code...";

// Mirror of ChatRequest.message max_length in backend/app/model/schemas/chat.py
const MAX_MESSAGE_LENGTH = 50_000;
// Reveal the counter only as the user nears the cap, so short messages stay uncluttered
const COUNTER_REVEAL_AT = Math.floor(MAX_MESSAGE_LENGTH * 0.9);

export function ChatWindow(): ReactElement {
	const { sessionId: sessionIdParam } = useParams();
	const sessionId = sessionIdParam ?? null;

	const [input, setInput] = useState("");
	const messagesEndRef = useRef<HTMLDivElement>(null);
	const textareaRef = useRef<HTMLTextAreaElement>(null);
	const fileInputRef = useRef<HTMLInputElement>(null);

	const scrollContainerRef = useRef<HTMLDivElement>(null);
	const shouldAutoScrollRef = useRef(true);

	const { data: session } = useSession(sessionId);
	const { data: sessionFiles } = useSessionFiles(sessionId);
	const queryClient = useQueryClient();

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
	const staged = useUploadStore((s) => s.staged);

	// Reveal streamed text at a steady pace instead of in network-chunk bursts
	const smoothStreamedText = useSmoothText(streamedText);
	const isVisuallyStreaming = isStreaming || smoothStreamedText !== streamedText;

	// Server-confirmed messages from React Query
	const serverMessages = session?.messages ?? [];

	// Group linked uploads by the user message they were attached to, for message chips
	const filesByMessage = useMemo(() => {
		const map = new Map<string, FileOut[]>();
		for (const f of sessionFiles?.files ?? []) {
			if (f.message_id !== null) {
				const list = map.get(f.message_id) ?? [];
				list.push(f);
				map.set(f.message_id, list);
			}
		}
		return map;
	}, [sessionFiles]);

	// Virtualize the (potentially huge) history so only visible bubbles mount and parse
	// Live rows (optimistic/streamed/tool pill) render below, un-virtualized
	// ! React Compiler cannot memoize TanStack Virtual's returned functions, so it safely bails on this component; the expensive child (MessageBubble) is memoized explicitly, so this is fine
	// eslint-disable-next-line react-hooks/incompatible-library
	const rowVirtualizer = useVirtualizer({
		count: serverMessages.length,
		getScrollElement: () => scrollContainerRef.current,
		estimateSize: () => 320,
		overscan: 2,
	});
	const virtualTotalSize = rowVirtualizer.getTotalSize();

	const showPendingUser = pendingUserMessage !== null && isStreaming;
	const showStreamedText = isStreaming || streamedText.length > 0;

	// Track whether user is near the bottom. Only auto-scroll when they are.
	const handleScroll = useCallback(() => {
		const container = scrollContainerRef.current;
		if (container === null) return;
		const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
		shouldAutoScrollRef.current = distanceFromBottom < 100;
	}, []);

	const handleFilesPicked = useCallback((files: FileList | null) => {
		if (files === null) return;
		const rejections = useUploadStore.getState().stageFiles([...files]);
		for (const rejection of rejections) toast.error(rejection);
	}, []);

	// A freshly opened session starts pinned to the bottom, no matter where the previous one sat
	useEffect(() => {
		shouldAutoScrollRef.current = true;
	}, [sessionId]);

	// Auto-scroll to bottom on new messages / streaming
	// virtualTotalSize in the deps re-pins to the bottom as dynamic row heights settle after a session loads
	useEffect(() => {
		if (!shouldAutoScrollRef.current) return;
		const container = scrollContainerRef.current;
		if (container !== null) container.scrollTop = container.scrollHeight;
	}, [serverMessages.length, smoothStreamedText, showPendingUser, virtualTotalSize]);

	// Auto-resize textarea
	useEffect(() => {
		const textarea = textareaRef.current;
		if (textarea !== null) {
			textarea.style.height = "auto";
			textarea.style.height = `${String(Math.min(textarea.scrollHeight, 200))}px`;
		}
	}, [input]);

	const submitMessage = useCallback(async () => {
		const trimmed = input.trim();
		if (trimmed.length === 0 || isStreaming || input.length > MAX_MESSAGE_LENGTH) return;

		const attachments = useUploadStore.getState().staged;
		let targetSessionId = sessionId;
		const attachedIds: string[] = [];

		if (attachments.length > 0) {
			// * Uploads need a real session id before the chat turn starts
			if (targetSessionId === null) {
				try {
					const created = await apiClient.post<{ id: string }>("/api/sessions", { title: "New Conversation" });
					targetSessionId = created.id;
				} catch {
					toast.error("Could not start the conversation - try again");
					return;
				}
			}
			const uploadTarget = targetSessionId;

			const results = await Promise.allSettled(
				attachments.map(async (att) => {
					// * Retry path: files that already made it up are reused, not re-sent
					if (att.status === "uploaded" && att.fileId !== undefined) return att.fileId;
					useUploadStore.getState().markUploading(att.id);
					const out = await uploadFile<FileOut>("/api/uploads", att.file, { scope: "session", session_id: uploadTarget }, (fraction) => {
						useUploadStore.getState().setProgress(att.id, fraction);
					});
					useUploadStore.getState().markUploaded(att.id, out.id);
					return out.id;
				})
			);

			results.forEach((result, i) => {
				const att = attachments[i];
				if (att === undefined) return;
				if (result.status === "fulfilled") {
					attachedIds.push(result.value);
				} else {
					const message = result.reason instanceof Error ? result.reason.message : "Upload failed";
					useUploadStore.getState().markFailed(att.id, message);
					toast.error(`${att.file.name}: ${message}`);
				}
			});
			// ! Abort before the message goes out - the draft stays intact
			if (results.some((r) => r.status === "rejected")) return;
		}

		setInput("");
		shouldAutoScrollRef.current = true;
		useChatStore.getState().addUserMessage(trimmed);
		sendMessage(trimmed, {
			...(targetSessionId !== null && { session_id: targetSessionId }),
			...(attachedIds.length > 0 && { attached_file_ids: attachedIds }),
		});
		useUploadStore.getState().clearStaged();
		// * Refetch session uploads so the just-linked files render as chips on the sent message
		if (targetSessionId !== null && attachedIds.length > 0) {
			void queryClient.invalidateQueries({ queryKey: ["uploads", "session", targetSessionId] });
		}
	}, [input, isStreaming, sessionId, sendMessage, queryClient]);

	const handleSubmit: SubmitEventHandler<HTMLFormElement> = useCallback(
		(e) => {
			e.preventDefault();
			void submitMessage();
		},
		[submitMessage]
	);

	const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = useCallback(
		(e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				void submitMessage();
			}
		},
		[submitMessage]
	);

	const charCount = input.length;
	const isOverLimit = charCount > MAX_MESSAGE_LENGTH;
	const showCounter = charCount >= COUNTER_REVEAL_AT;

	return (
		<div className="flex h-full min-w-0 flex-col">
			{/* Messages area */}
			<div ref={scrollContainerRef} onScroll={handleScroll} className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-6">
				<div className="mx-auto min-w-0 max-w-3xl">
					{serverMessages.length === 0 && !isStreaming && pendingUserMessage === null && (
						<div className="py-24 text-center">
							<h2 className="text-2xl font-bold tracking-tight">MPMB Copilot</h2>
							<p className="mt-2 text-muted-foreground">Ask me about writing MPMB automation scripts for D&amp;D 5e character sheets.</p>
						</div>
					)}

					{/* Virtualized history: only visible bubbles mount (and parse their markdown) */}
					<div style={{ height: `${String(virtualTotalSize)}px`, position: "relative" }}>
						{rowVirtualizer.getVirtualItems().map((virtualRow) => {
							const msg = serverMessages[virtualRow.index];
							if (msg === undefined) return null;
							return (
								<div
									key={msg.id}
									data-index={virtualRow.index}
									ref={rowVirtualizer.measureElement}
									style={{
										position: "absolute",
										top: 0,
										left: 0,
										width: "100%",
										transform: `translateY(${String(virtualRow.start)}px)`,
									}}>
									<div className="pb-6">
										<MessageBubble
											messageId={msg.id}
											sessionId={msg.session_id}
											feedback={msg.feedback}
											role={msg.role}
											content={msg.content.text}
											sources={msg.content.sources}
											tools={msg.meta_data.tools}
											cacheReadTokens={msg.meta_data.usage?.cache_read_tokens}
											stopReason={msg.stop_reason ?? undefined}
											attachments={filesByMessage.get(msg.id)}
										/>
									</div>
								</div>
							);
						})}
					</div>

					{/* Live rows render normally below the virtualizer */}
					<div className="space-y-6">
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
					</div>
					<div ref={messagesEndRef} />
				</div>
			</div>

			{/* Input area */}
			<div className="border-t border-border bg-background px-4 py-3">
				<div className="mx-auto min-w-0 max-w-3xl">
					<AttachmentChips />
					<form
						onSubmit={handleSubmit}
						onDragOver={(e) => {
							e.preventDefault();
						}}
						onDrop={(e) => {
							e.preventDefault();
							handleFilesPicked(e.dataTransfer.files);
						}}
						className="flex min-w-0 items-end gap-2">
						<input
							ref={fileInputRef}
							type="file"
							multiple
							accept={UPLOAD_EXTENSIONS.join(",")}
							className="hidden"
							onChange={(e) => {
								handleFilesPicked(e.target.files);
								e.target.value = "";
							}}
						/>
						<button
							type="button"
							onClick={() => {
								fileInputRef.current?.click();
							}}
							disabled={isStreaming}
							aria-label="Attach files"
							className="shrink-0 rounded-lg border border-input p-3 text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50">
							<Paperclip className="size-4" />
						</button>
						<textarea
							ref={textareaRef}
							value={input}
							onChange={(e) => {
								setInput(e.target.value);
							}}
							onKeyDown={handleKeyDown}
							placeholder="Ask about MPMB scripting..."
							rows={1}
							aria-invalid={isOverLimit}
							className={cn(
								"flex-1 resize-none rounded-lg border bg-background px-4 py-3",
								"text-sm placeholder:text-muted-foreground",
								"focus:outline-none focus:ring-2",
								isOverLimit ? "border-destructive focus:ring-destructive" : "border-input focus:ring-ring"
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
								disabled={input.trim().length === 0 || isOverLimit || staged.some((a) => a.status === "uploading")}
								className="shrink-0 rounded-lg bg-primary p-3 text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
								<Send className="size-4" />
							</button>
						)}
					</form>

					{showCounter && (
						<p className={cn("mt-1.5 text-right text-xs tabular-nums", isOverLimit ? "text-destructive" : "text-muted-foreground")}>
							{isOverLimit ? (
								<span role="alert">
									{(charCount - MAX_MESSAGE_LENGTH).toLocaleString()} over the {MAX_MESSAGE_LENGTH.toLocaleString()} character limit
								</span>
							) : (
								<>
									{charCount.toLocaleString()} / {MAX_MESSAGE_LENGTH.toLocaleString()}
								</>
							)}
						</p>
					)}
				</div>
			</div>
		</div>
	);
}

import { Check, Copy, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { useClearFeedback, useSetFeedback } from "@/hooks/use-feedback";
import { cn } from "@/lib/utils";
import type { MessageFeedback } from "@/types/session";
import type { ReactElement } from "react";

interface MessageActionsProps {
	readonly sessionId: string;
	readonly messageId: string;
	readonly content: string;
	readonly feedback: MessageFeedback | null;
}

export function MessageActions({ sessionId, messageId, content, feedback }: MessageActionsProps): ReactElement {
	const [copied, setCopied] = useState(false);
	const [noteOpen, setNoteOpen] = useState(false);
	const [note, setNote] = useState(feedback?.note ?? "");

	const setFeedback = useSetFeedback(sessionId);
	const clearFeedback = useClearFeedback(sessionId);
	const rating = feedback?.rating ?? null;

	const onError = (e: Error): void => {
		toast.error(e.message);
	};

	const copy = async (): Promise<void> => {
		await navigator.clipboard.writeText(content);
		setCopied(true);
		setTimeout(() => {
			setCopied(false);
		}, 1500);
	};

	const vote = (next: "up" | "down"): void => {
		if (rating === next) {
			clearFeedback.mutate(messageId, { onError });
			setNoteOpen(false);
			return;
		}
		setFeedback.mutate({ messageId, rating: next, note: next === "down" ? note || undefined : undefined }, { onError });
		setNoteOpen(next === "down");
	};

	const saveNote = (): void => {
		setFeedback.mutate({ messageId, rating: "down", note: note || undefined }, { onError });
		setNoteOpen(false);
	};

	return (
		<div className="flex items-center gap-1 text-muted-foreground">
			<button
				type="button"
				title="Copy"
				onClick={() => {
					void copy();
				}}
				className="rounded p-1 hover:bg-muted">
				{copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
			</button>
			<button
				type="button"
				title="Good response"
				onClick={() => {
					vote("up");
				}}
				className={cn("rounded p-1 hover:bg-muted", rating === "up" && "text-primary")}>
				<ThumbsUp className="size-3.5" />
			</button>
			<button
				type="button"
				title="Bad response"
				onClick={() => {
					vote("down");
				}}
				className={cn("rounded p-1 hover:bg-muted", rating === "down" && "text-destructive")}>
				<ThumbsDown className="size-3.5" />
			</button>
			{noteOpen && (
				<span className="flex items-center gap-1">
					<input
						value={note}
						maxLength={2000}
						placeholder="What went wrong? (optional)"
						onChange={(e) => {
							setNote(e.target.value);
						}}
						className="rounded border border-input bg-background px-2 py-0.5 text-xs"
					/>
					<button type="button" onClick={saveNote} className="rounded px-1.5 py-0.5 text-xs hover:bg-muted">
						Save
					</button>
				</span>
			)}
		</div>
	);
}

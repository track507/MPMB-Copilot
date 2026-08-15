import { Circle, LogOut, Moon, Sun } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useMatches, useNavigate, useParams } from "@tanstack/react-router";
import { useIndexStatus } from "@/hooks/use-settings";
import { useSession } from "@/hooks/use-sessions";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";
import { useLogout } from "@/hooks/use-auth";

export function TopBar(): ReactElement {
	const { data: indexStatus } = useIndexStatus();
	const { sessionId } = useParams({ strict: false });
	const { data: session } = useSession(sessionId ?? null);
	const matches = useMatches();
	// * Deepest route that names itself owns the header; a chat route defers to its live session title
	const page = matches.findLast((match) => match.staticData.title !== undefined)?.staticData;
	const isChat = matches.some((match) => match.staticData.chat === true);
	const title = isChat ? (session?.title ?? "New chat") : (page?.title ?? "MPMB Copilot");
	const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
	const logout = useLogout();
	const navigate = useNavigate();

	const toggleTheme = useCallback(() => {
		setDark((prev) => {
			const next = !prev;
			document.documentElement.classList.toggle("dark", next);
			return next;
		});
	}, []);

	useEffect(() => {
		// Persist theme preference
		if (dark) {
			document.documentElement.classList.add("dark");
		} else {
			document.documentElement.classList.remove("dark");
		}
	}, [dark]);

	const statusColor =
		indexStatus?.status === "ready" ? "text-green-500" : indexStatus?.status === "indexing" ? "text-yellow-500" : "text-muted-foreground/40";

	const statusLabel =
		indexStatus?.status === "ready"
			? `Index ready (${String(indexStatus.total_vectors)} vectors)`
			: indexStatus?.status === "indexing"
				? "Indexing..."
				: indexStatus?.status === "empty"
					? "Index empty"
					: "Index unavailable";

	return (
		<header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-6">
			<div className="flex min-w-0 flex-col justify-center">
				<span className="truncate text-sm font-semibold leading-tight">{title}</span>
				{/* ? Index state belongs to chat, where retrieval runs; other pages get their own subtitle */}
				{isChat ? (
					<span className="flex items-center gap-1.5 text-xs text-muted-foreground">
						<Circle className={cn("size-2 shrink-0 fill-current", statusColor)} />
						{statusLabel}
					</span>
				) : page?.description === undefined ? null : (
					<span className="truncate text-xs text-muted-foreground">{page.description}</span>
				)}
			</div>

			<div className="flex items-center gap-1">
				<button
					type="button"
					onClick={toggleTheme}
					className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground">
					{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
				</button>
				<button
					type="button"
					title="Sign out"
					onClick={() => {
						logout.mutate(undefined, {
							onSettled: () => {
								void navigate({ to: "/login" });
							},
						});
					}}
					className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground">
					<LogOut className="size-4" />
				</button>
			</div>
		</header>
	);
}

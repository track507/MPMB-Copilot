import { Circle, Moon, Sun } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { useIndexStatus } from "@/hooks/use-settings";
import { useSession } from "@/hooks/use-sessions";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

export function TopBar(): ReactElement {
	const { data: indexStatus } = useIndexStatus();
	const { sessionId } = useParams();
	const { data: session } = useSession(sessionId ?? null);
	const title = session?.title ?? "MPMB Copilot";
	const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));

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
				<span className="flex items-center gap-1.5 text-xs text-muted-foreground">
					<Circle className={cn("size-2 shrink-0 fill-current", statusColor)} />
					{statusLabel}
				</span>
			</div>

			<button
				type="button"
				onClick={toggleTheme}
				className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground">
				{dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
			</button>
		</header>
	);
}

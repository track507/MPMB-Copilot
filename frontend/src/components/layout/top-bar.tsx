import { Circle, Moon, Sun } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useIndexStatus } from "@/hooks/use-settings";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

export function TopBar(): ReactElement {
	const { data: indexStatus } = useIndexStatus();
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
			<div className="flex items-center gap-2 text-xs text-muted-foreground">
				<Circle className={cn("size-2.5 fill-current", statusColor)} />
				{statusLabel}
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

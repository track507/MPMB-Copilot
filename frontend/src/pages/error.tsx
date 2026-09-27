import { Link } from "@tanstack/react-router";
import type { ErrorComponentProps } from "@tanstack/react-router";
import type { ReactElement } from "react";

/**
 * The designed error page, in place of the router's built-in CatchBoundary
 */
export default function ErrorPage({ error, reset }: ErrorComponentProps): ReactElement {
	const detail = error instanceof Error ? error.message : String(error);

	return (
		<div className="mx-auto max-w-md py-24 text-center">
			<h1 className="text-6xl font-bold text-muted-foreground/30">Oops</h1>
			<p className="mt-4 text-lg text-muted-foreground">Something broke on this page</p>

			{import.meta.env.DEV && (
				<pre className="mt-6 overflow-x-auto rounded-md bg-muted/60 p-3 text-left text-xs whitespace-pre-wrap text-muted-foreground">{detail}</pre>
			)}

			<div className="mt-6 flex items-center justify-center gap-2">
				<button
					type="button"
					onClick={reset}
					className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
					Try again
				</button>
				<Link to="/" className="rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-muted">
					Go home
				</Link>
			</div>
		</div>
	);
}

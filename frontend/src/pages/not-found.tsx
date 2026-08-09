import { Link } from "@tanstack/react-router";
import type { ReactElement } from "react";

export default function NotFoundPage(): ReactElement {
	return (
		<div className="mx-auto max-w-md py-24 text-center">
			<h1 className="text-6xl font-bold text-muted-foreground/30">404</h1>
			<p className="mt-4 text-lg text-muted-foreground">Page not found</p>
			<Link
				to="/"
				className="mt-6 inline-block rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90">
				Go home
			</Link>
		</div>
	);
}

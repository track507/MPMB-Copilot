import { Outlet } from "@tanstack/react-router";
import type { ReactElement } from "react";

// TODO: Add subnavigation
export function AdminLayout(): ReactElement {
	return (
		<div className="mx-auto max-w-4xl px-4 py-8">
			<h1 className="text-2xl font-bold tracking-tight">Admin</h1>
			<p className="mt-1 text-sm text-muted-foreground">Instance configuration and operations.</p>
			<div className="mt-6">
				<Outlet />
			</div>
		</div>
	);
}

import { Outlet } from "@tanstack/react-router";
import type { ReactElement } from "react";

export function AdminLayout(): ReactElement {
	return (
		<div className="mx-auto w-full max-w-6xl px-4 py-8">
			<Outlet />
		</div>
	);
}

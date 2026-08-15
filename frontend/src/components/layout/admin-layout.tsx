import { Outlet } from "@tanstack/react-router";
import type { ReactElement } from "react";

// * Wide console shell (the top bar carries the "Admin" title); subnav is a follow-up
export function AdminLayout(): ReactElement {
	return (
		<div className="mx-auto w-full max-w-6xl px-4 py-8">
			<Outlet />
		</div>
	);
}

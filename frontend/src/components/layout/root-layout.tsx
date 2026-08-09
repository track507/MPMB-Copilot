import { Outlet } from "@tanstack/react-router";
import { Toaster } from "sonner";
import { SidebarNav } from "./sidebar-nav";
import { TopBar } from "./top-bar";
import type { ReactElement } from "react";

export default function RootLayout(): ReactElement {
	return (
		<div className="flex h-screen overflow-hidden bg-background text-foreground">
			<SidebarNav />

			<div className="flex min-w-0 flex-1 flex-col overflow-hidden">
				<TopBar />

				<main className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto">
					<Outlet />
				</main>
			</div>

			<Toaster richColors closeButton position="bottom-right" />
		</div>
	);
}

import { useCallback } from "react";
import { NavLink, useNavigate, useParams } from "react-router";
import { MessageSquarePlus, Settings, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useSessions, useDeleteSession } from "@/hooks/use-sessions";
import type { ReactElement } from "react";

export function SidebarNav(): ReactElement {
	const navigate = useNavigate();
	const { sessionId: activeSessionId } = useParams();

	const { data: sessionList } = useSessions();
	const deleteSession = useDeleteSession();

	// ? New Chat just opens a blank window
	// ? The session is created by the backend on the first message (see use-chat), avoiding empty throwaway sessions
	const handleNewChat = useCallback(() => {
		void navigate("/");
	}, [navigate]);

	const handleDelete = useCallback(
		(e: React.MouseEvent, sessionId: string) => {
			e.preventDefault();
			e.stopPropagation();
			deleteSession.mutate(sessionId, {
				onSuccess: () => {
					if (activeSessionId === sessionId) {
						void navigate("/");
					}
				},
				onError: () => {
					toast.error("Failed to delete session");
				},
			});
		},
		[deleteSession, activeSessionId, navigate]
	);

	const sessions = sessionList?.sessions ?? [];

	return (
		<aside className="flex w-60 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
			{/* Branding */}
			<div className="flex h-14 shrink-0 items-center gap-3 border-b border-sidebar-border px-4">
				<div className="h-6 w-1.5 rounded-sm bg-primary" />
				<span className="text-sm font-bold tracking-tight">MPMB Copilot</span>
			</div>

			{/* New chat button */}
			<div className="p-3">
				<button
					type="button"
					onClick={handleNewChat}
					className="flex w-full items-center gap-2 rounded-md border border-sidebar-border px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent">
					<MessageSquarePlus className="size-4" />
					New Chat
				</button>
			</div>

			{/* Session list */}
			<nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
				{sessions.map((session) => (
					<NavLink
						key={session.id}
						to={`/chat/${session.id}`}
						className={cn(
							"group flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors",
							activeSessionId === session.id
								? "bg-sidebar-accent text-sidebar-accent-foreground"
								: "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
						)}>
						<span className="truncate">{session.title}</span>
						<button
							type="button"
							onClick={(e) => {
								handleDelete(e, session.id);
							}}
							className="shrink-0 opacity-0 transition-opacity group-hover:opacity-100">
							<Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
						</button>
					</NavLink>
				))}
			</nav>

			{/* Settings link */}
			<div className="shrink-0 border-t border-sidebar-border p-3">
				<NavLink
					to="/settings"
					className={({ isActive }) =>
						cn(
							"flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
							isActive
								? "bg-sidebar-accent text-sidebar-accent-foreground"
								: "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
						)
					}>
					<Settings className="size-4" />
					Settings
				</NavLink>
			</div>
		</aside>
	);
}

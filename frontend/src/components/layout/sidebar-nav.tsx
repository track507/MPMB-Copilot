import { useCallback, useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router";
import { Check, MessageSquarePlus, Pencil, Settings, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useSessions, useDeleteSession, useUpdateSession } from "@/hooks/use-sessions";
import type { Session } from "@/types/session";
import type { ReactElement } from "react";
import { useIsAdmin } from "@/hooks/use-auth";

export function SidebarNav(): ReactElement {
	const navigate = useNavigate();
	const { sessionId: activeSessionId } = useParams();

	const { data: sessionList } = useSessions();
	const deleteSession = useDeleteSession();

	const { isAdmin } = useIsAdmin();

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
					<SessionRow key={session.id} session={session} isActive={activeSessionId === session.id} onDelete={handleDelete} />
				))}
			</nav>

			{/* Settings link (admin only) */}
			{isAdmin && (
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
			)}
		</aside>
	);
}

interface SessionRowProps {
	readonly session: Session;
	readonly isActive: boolean;
	readonly onDelete: (e: React.MouseEvent, sessionId: string) => void;
}

function SessionRow({ session, isActive, onDelete }: SessionRowProps): ReactElement {
	const [editing, setEditing] = useState(false);
	const [draft, setDraft] = useState(session.title);
	const update = useUpdateSession(session.id);

	// * Seed the draft from the current title each time editing begins, so a server-side title change (e.g. auto-title landing) is never stale
	const startEditing = useCallback(() => {
		setDraft(session.title);
		setEditing(true);
	}, [session.title]);

	const save = useCallback(() => {
		setEditing(false);
		const trimmed = draft.trim();
		if (trimmed.length === 0 || trimmed === session.title) {
			setDraft(session.title);
			return;
		}
		update.mutate(
			{ title: trimmed },
			{
				onError: () => {
					toast.error("Failed to rename session");
					setDraft(session.title);
				},
			}
		);
	}, [draft, session.title, update]);

	const rowClass = cn(
		"group flex items-center rounded-md text-sm transition-colors",
		isActive
			? "bg-sidebar-accent text-sidebar-accent-foreground"
			: "text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
	);

	if (editing) {
		return (
			<div className={rowClass}>
				<input
					autoFocus
					value={draft}
					maxLength={255}
					onChange={(e) => {
						setDraft(e.target.value);
					}}
					onBlur={save}
					onKeyDown={(e) => {
						if (e.key === "Enter") {
							e.preventDefault();
							save();
						} else if (e.key === "Escape") {
							setEditing(false);
							setDraft(session.title);
						}
					}}
					className="min-w-0 flex-1 bg-transparent px-3 py-2 focus:outline-none"
				/>
				<div className="flex shrink-0 items-center gap-1 pr-2">
					<button
						type="button"
						onMouseDown={(e) => {
							e.preventDefault();
						}}
						onClick={save}
						title="Save">
						<Check className="size-3.5 text-muted-foreground hover:text-primary" />
					</button>
				</div>
			</div>
		);
	}

	return (
		<div className={rowClass}>
			<NavLink to={`/chat/${session.id}`} className="min-w-0 flex-1 truncate px-3 py-2">
				{session.title}
			</NavLink>
			<div className="flex shrink-0 items-center gap-1 pr-2 opacity-0 transition-opacity group-hover:opacity-100">
				<button type="button" onClick={startEditing} title="Rename">
					<Pencil className="size-3.5 text-muted-foreground hover:text-foreground" />
				</button>
				<button
					type="button"
					onClick={(e) => {
						onDelete(e, session.id);
					}}
					title="Delete">
					<Trash2 className="size-3.5 text-muted-foreground hover:text-destructive" />
				</button>
			</div>
		</div>
	);
}

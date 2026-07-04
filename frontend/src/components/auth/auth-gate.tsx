import { Loader2 } from "lucide-react";
import { Navigate } from "react-router";
import { useAuthState } from "@/hooks/use-auth";
import type { ReactElement, ReactNode } from "react";

/** Routes unauthenticated visitors to /setup or /login; renders children once authenticated */
export function AuthGate({ children }: { readonly children: ReactNode }): ReactElement {
	const { data, isLoading, isError } = useAuthState();

	if (isLoading) {
		return (
			<div className="flex h-screen items-center justify-center">
				<Loader2 className="size-6 animate-spin text-muted-foreground" />
			</div>
		);
	}
	if (isError || data === undefined) {
		return (
			<div className="flex h-screen items-center justify-center text-sm text-muted-foreground">
				Backend unavailable - check that the server is running, then reload.
			</div>
		);
	}
	if (data.state === "setup_required") return <Navigate to="/setup" replace />;
	if (data.state === "login_required") return <Navigate to="/login" replace />;
	return <>{children}</>;
}

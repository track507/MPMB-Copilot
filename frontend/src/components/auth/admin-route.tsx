import { lazy, Suspense } from "react";
import { useIsAdmin } from "@/hooks/use-auth";
import type { ReactElement, ReactNode } from "react";

const NotFoundPage = lazy(async () => import("@/pages/not-found"));

/** Renders the exact 404 page for non-admins: an admin route must be indistinguishable from a route that does not exist. */
export function AdminRoute({ children }: { readonly children: ReactNode }): ReactElement | null {
	const { isAdmin, isLoading } = useIsAdmin();

	// ? Under the AuthGate the auth state is already cached; this only guards a first-render flash
	if (isLoading) return null;

	if (!isAdmin) {
		return (
			<Suspense fallback={null}>
				<NotFoundPage />
			</Suspense>
		);
	}

	return <>{children}</>;
}

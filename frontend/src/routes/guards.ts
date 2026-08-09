import { notFound, redirect } from "@tanstack/react-router";
import { authStateQueryOptions } from "@/hooks/use-auth";
import type { QueryClient } from "@tanstack/react-query";

export async function requireAuth(queryClient: QueryClient): Promise<void> {
	const auth = await queryClient.ensureQueryData(authStateQueryOptions).catch(() => null);
	if (auth?.state !== "authenticated") {
		// ! First run with no admin needs setup; every other unauthenticated state goes to login
		throw redirect({ to: auth?.state === "setup_required" ? "/setup" : "/login" });
	}
}

// ! Non-admins get the 404 page (no route discoverability)
export async function requireAdmin(queryClient: QueryClient): Promise<void> {
	const auth = await queryClient.ensureQueryData(authStateQueryOptions).catch(() => null);
	if (auth?.user?.role !== "admin") {
		// * notFound() renders the notFoundComponent in place (no route path needed)
		throw notFound();
	}
}

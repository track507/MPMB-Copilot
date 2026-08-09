import { QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/http";

// Single app-wide client: the router (loaders/guards via ensureQueryData) and the component hooks (useQuery) must share one cache
export const queryClient = new QueryClient({
	queryCache: new QueryCache({
		onError: (error) => {
			// ! Session died mid-use: refetch auth state so the route guards bounce to /login
			if (error instanceof ApiError && error.status === 401) {
				void queryClient.invalidateQueries({ queryKey: ["auth-state"] });
			}
		},
	}),
	defaultOptions: {
		queries: {
			staleTime: 5 * 60 * 1000,
			retry: 1,
			refetchOnWindowFocus: true,
		},
	},
});

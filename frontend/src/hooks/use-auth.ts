import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { AuthState, AuthUser, LoginRequest, SetupRequest } from "@/types/auth";

export const AUTH_STATE_KEY = ["auth-state"] as const;

export function useAuthState(): ReturnType<typeof useQuery<AuthState>> {
	return useQuery({
		queryKey: AUTH_STATE_KEY,
		queryFn: async () => apiClient.get<AuthState>("/api/auth/state"),
		staleTime: 60_000,
		retry: false,
	});
}

export function useLogin(): ReturnType<typeof useMutation<AuthUser, Error, LoginRequest>> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (body: LoginRequest) => apiClient.post<AuthUser>("/api/auth/login", body),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: AUTH_STATE_KEY });
		},
	});
}

export function useSetup(): ReturnType<typeof useMutation<AuthUser, Error, SetupRequest>> {
	const queryClient = useQueryClient();
	return useMutation({
		mutationFn: async (body: SetupRequest) => apiClient.post<AuthUser>("/api/auth/setup", body),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: AUTH_STATE_KEY });
		},
	});
}

export function useLogout(): ReturnType<typeof useMutation<undefined, Error, void>> {
	const queryClient = useQueryClient();
	return useMutation({
		// ? 204 response: the client resolves undefined, so undefined is the honest data type (void is invalid here per lint)
		mutationFn: async () => apiClient.post("/api/auth/logout", {}),
		onSuccess: () => {
			// ! Drop every cached query: nothing fetched while logged in may survive logout
			queryClient.clear();
		},
	});
}

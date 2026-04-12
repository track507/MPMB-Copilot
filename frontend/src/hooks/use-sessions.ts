import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Session, SessionCreate, SessionDetail, SessionListResponse, SessionUpdate } from "@/types/session";

const SESSIONS_KEY = ["sessions"] as const;

export function useSessions(limit = 50, offset = 0): ReturnType<typeof useQuery<SessionListResponse>> {
	return useQuery({
		queryKey: [...SESSIONS_KEY, limit, offset],
		queryFn: async () => apiClient.get<SessionListResponse>(`/api/sessions?limit=${String(limit)}&offset=${String(offset)}`),
	});
}

export function useSession(sessionId: string | null): ReturnType<typeof useQuery<SessionDetail>> {
	return useQuery({
		queryKey: [...SESSIONS_KEY, sessionId],
		queryFn: async () => apiClient.get<SessionDetail>(`/api/sessions/${sessionId ?? ""}`),
		enabled: sessionId !== null,
	});
}

export function useCreateSession(): ReturnType<typeof useMutation<Session, Error, SessionCreate>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (data: SessionCreate) => apiClient.post<Session>("/api/sessions", data),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
		},
	});
}

export function useUpdateSession(sessionId: string): ReturnType<typeof useMutation<Session, Error, SessionUpdate>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (data: SessionUpdate) => apiClient.put<Session>(`/api/sessions/${sessionId}`, data),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
		},
	});
}

export function useDeleteSession(): ReturnType<typeof useMutation<undefined, Error, string>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (sessionId: string) => apiClient.delete<undefined>(`/api/sessions/${sessionId}`),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: SESSIONS_KEY });
		},
	});
}

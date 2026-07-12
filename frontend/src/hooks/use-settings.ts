import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Settings, SettingsUpdate, IndexStatus, IndexTriggerResponse, TaskStatus, HealthResponse, CapabilityEnvelope } from "@/types/settings";

const SETTINGS_KEY = ["settings"] as const;
const CAPABILITIES_KEY = ["capabilities"] as const;
const INDEX_KEY = ["index-status"] as const;
const HEALTH_KEY = ["health"] as const;

export function useSettings(): ReturnType<typeof useQuery<Settings>> {
	return useQuery({
		queryKey: SETTINGS_KEY,
		queryFn: async () => apiClient.get<Settings>("/api/settings"),
	});
}

export function useCapabilities(): ReturnType<typeof useQuery<CapabilityEnvelope>> {
	return useQuery({
		queryKey: CAPABILITIES_KEY,
		queryFn: async () => apiClient.get<CapabilityEnvelope>("/api/capabilities"),
		// ? Catalogs change rarely and the backend caches model fetches for an hour
		staleTime: 30 * 60_000,
	});
}

export function useUpdateSettings(): ReturnType<typeof useMutation<Settings, Error, SettingsUpdate>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async (data: SettingsUpdate) => apiClient.patch<Settings>("/api/settings", data),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: SETTINGS_KEY });
		},
	});
}

export function useIndexStatus(): ReturnType<typeof useQuery<IndexStatus>> {
	return useQuery({
		queryKey: INDEX_KEY,
		queryFn: async () => apiClient.get<IndexStatus>("/api/index/status"),
		// ? Poll fast while an index runs so gating and the top-bar stay honest
		refetchInterval: (query) => (query.state.data?.status === "indexing" ? 5_000 : 30_000),
	});
}

export function useTriggerIndex(): ReturnType<typeof useMutation<IndexTriggerResponse, Error, { force: boolean }>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async ({ force }: { force: boolean }) => apiClient.post<IndexTriggerResponse>("/api/index", { force_reindex: force }),
		onSuccess: async () => {
			await queryClient.invalidateQueries({ queryKey: INDEX_KEY });
		},
	});
}

export function useHealth(): ReturnType<typeof useQuery<HealthResponse>> {
	return useQuery({
		queryKey: HEALTH_KEY,
		queryFn: async () => apiClient.get<HealthResponse>("/api/health"),
		refetchInterval: 60_000,
	});
}

export function useIndexTask(taskId: string | null): ReturnType<typeof useQuery<TaskStatus>> {
	return useQuery({
		queryKey: ["index-task", taskId],
		queryFn: async () => apiClient.get<TaskStatus>(`/api/tasks/${taskId ?? ""}`),
		enabled: taskId !== null,
		refetchInterval: (query) => {
			const s = query.state.data?.status;
			return s === undefined || s === "pending" || s === "running" ? 2_000 : false;
		},
	});
}

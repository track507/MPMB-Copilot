import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Settings, SettingsUpdate, IndexStatus, HealthResponse, ModelCatalog, EmbeddingCatalog } from "@/types/settings";

const SETTINGS_KEY = ["settings"] as const;
const MODELS_KEY = ["models"] as const;
const EMBEDDING_MODELS_KEY = ["embedding-models"] as const;
const INDEX_KEY = ["index-status"] as const;
const HEALTH_KEY = ["health"] as const;

export function useSettings(): ReturnType<typeof useQuery<Settings>> {
	return useQuery({
		queryKey: SETTINGS_KEY,
		queryFn: async () => apiClient.get<Settings>("/api/settings"),
	});
}

export function useModelCatalog(): ReturnType<typeof useQuery<ModelCatalog>> {
	return useQuery({
		queryKey: MODELS_KEY,
		queryFn: async () => apiClient.get<ModelCatalog>("/api/models"),
		// ? Model lists change rarely and the backend caches for an hour; keep it fresh-ish across mounts
		staleTime: 30 * 60_000,
	});
}

export function useEmbeddingCatalog(): ReturnType<typeof useQuery<EmbeddingCatalog>> {
	return useQuery({
		queryKey: EMBEDDING_MODELS_KEY,
		queryFn: async () => apiClient.get<EmbeddingCatalog>("/api/embedding-models"),
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
		refetchInterval: 30_000,
	});
}

export function useTriggerIndex(): ReturnType<typeof useMutation<{ task_id: string }, Error, void>> {
	const queryClient = useQueryClient();

	return useMutation({
		mutationFn: async () => apiClient.post<{ task_id: string }>("/api/index", {}),
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

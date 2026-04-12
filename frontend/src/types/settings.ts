/** Mirrors backend Settings dataclass fields. */

export interface Settings {
	readonly default_llm_provider: string;
	readonly default_model: string;
	readonly temperature: number;
	readonly max_tokens: number;
	readonly default_edition: string;
	readonly top_k_results: number;
	readonly similarity_threshold: number;
	readonly context_window_size: number;
	readonly retrieval_mode: "single" | "dual" | "auto";
	readonly intent_method: "embedding" | "rule" | "hybrid";
	readonly intent_confidence_threshold: number;
	readonly intent_confidence_margin: number;
	readonly tier_budgets: Record<string, TierBudget>;
	readonly enable_tool_use: boolean;
	readonly max_tool_calls: number;
	readonly tool_search_limit: number;
	readonly enable_extended_thinking: boolean;
	readonly thinking_budget_tokens: number;
	readonly system_prompt: string | null;
}

export interface TierBudget {
	readonly authoritative: number;
	readonly examples: number;
}

export type SettingsUpdate = Partial<Settings>;

export interface IndexStatus {
	readonly collection_name: string;
	readonly total_vectors: number;
	readonly indexed_files: number;
	readonly last_updated: string | null;
	readonly status: "ready" | "indexing" | "stale" | "empty" | "error";
}

export interface HealthResponse {
	readonly status: "healthy" | "degraded" | "unhealthy";
	readonly environment: string;
	readonly version: string;
	readonly timestamp: string;
	readonly services: Record<string, ServiceStatus>;
}

export interface ServiceStatus {
	readonly status: string;
	readonly message?: string | undefined;
}

/** Mirrors backend Settings dataclass fields. */

export interface Settings {
	readonly default_llm_provider: string;
	readonly default_model: string;
	readonly temperature: number;
	readonly max_tokens: number;
	readonly default_effort: string;
	readonly embedding_provider: string;
	readonly embedding_model: string;
	readonly anthropic_cheap_model: string;
	readonly openai_cheap_model: string;
	readonly ollama_cheap_model: string;
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
	readonly rerank_enabled: boolean;
	readonly rerank_provider: string;
	readonly rerank_model: string;
	readonly rerank_candidate_k: number;
	readonly system_prompt: string | null;
}

export interface TierBudget {
	readonly authoritative: number;
	readonly examples: number;
}

export type SettingsUpdate = Partial<Settings>;

/**
 * One selectable model from the backend catalog
 * Shapes are intentionally open (`string`, `string[]`) so new models or effort tiers flow through from the
 * backend with no frontend changes - never enumerate these as literal unions
 */
export interface ModelOption {
	readonly id: string;
	readonly label: string;
	readonly effort: readonly string[];
}

/** Per-provider model lists (the generation entries in the capabilities envelope). Empty list = free-form input. */
export interface ModelCatalog {
	readonly anthropic: readonly ModelOption[];
	readonly openai: readonly ModelOption[];
	readonly ollama: readonly ModelOption[];
}

/** One selectable embedding model (an embedding entry in the capabilities envelope) */
export interface EmbeddingModelOption {
	readonly provider: string;
	readonly id: string;
	readonly label: string;
	readonly dimension: number;
	readonly multilingual: boolean;
	readonly pinned: boolean;
	readonly status: "ready" | "needs_key" | "installable";
}

/** One selectable reranker from the capabilities envelope */
export interface RerankModelOption {
	readonly provider: string;
	readonly id: string;
	readonly label: string;
	readonly pinned: boolean;
	readonly status: "ready" | "needs_key" | "installable";
}

/** One selectable vector store from the capabilities envelope */
export interface VectorStoreOption {
	readonly provider: string;
	readonly id: string;
	readonly label: string;
	readonly pinned: boolean;
	readonly status: "ready" | "needs_key" | "installable";
}

/** GET /api/capabilities - one envelope per capability
 * `kind` tells the UI how to render entries
 */
export interface CapabilityEnvelope {
	readonly generation: {
		readonly label: string;
		readonly kind: "live_models";
		readonly entries: ModelCatalog;
		readonly current: { readonly provider: string; readonly model: string; readonly effort: string };
	};
	readonly embedding: {
		readonly label: string;
		readonly kind: "curated";
		readonly entries: readonly EmbeddingModelOption[];
		readonly current: { readonly provider: string; readonly model: string };
	};
	readonly rerank: {
		readonly label: string;
		readonly kind: "curated";
		readonly entries: readonly RerankModelOption[];
		readonly current: { readonly provider: string; readonly model: string; readonly enabled: boolean; readonly candidate_k: number };
	};
	readonly vector_store: {
		readonly label: string;
		readonly kind: "curated";
		readonly entries: readonly VectorStoreOption[];
		readonly current: { readonly provider: string };
	};
}

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

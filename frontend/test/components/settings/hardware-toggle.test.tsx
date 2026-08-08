import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPanel } from "@/components/settings/settings-panel";
import type { CapabilityEnvelope } from "@/types/settings";
const mocks = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/http", () => ({ apiClient: { get: mocks.get, patch: vi.fn(), post: vi.fn() }, ApiError: Error }));

const SETTINGS = {
	default_llm_provider: "anthropic",
	default_model: "claude-sonnet-4-6",
	temperature: 0.2,
	max_tokens: 8000,
	default_effort: "high",
	embedding_provider: "fastembed",
	embedding_model: "BAAI/bge-small-en-v1.5",
	anthropic_cheap_model: "claude-haiku-4-5",
	openai_cheap_model: "gpt-5.4-mini",
	ollama_cheap_model: "",
	default_edition: "2014",
	top_k_results: 8,
	similarity_threshold: 0.5,
	retrieval_mode: "dual",
	rerank_enabled: true,
	rerank_provider: "fastembed",
	rerank_model: "Xenova/ms-marco-MiniLM-L-6-v2",
	rerank_candidate_k: 24,
	enable_tool_use: true,
	enable_extended_thinking: false,
	inference_device: "cpu",
} as const;

function capabilities(gpuStatus: "ready" | "installable"): CapabilityEnvelope {
	return {
		generation: {
			label: "Generation (LLM)",
			kind: "live_models",
			entries: { anthropic: [], openai: [], ollama: [] },
			current: { provider: "anthropic", model: "claude-sonnet-4-6", effort: "high" },
		},
		embedding: {
			label: "Embedding",
			kind: "curated",
			entries: [
				{ provider: "fastembed", id: "BAAI/bge-small-en-v1.5", label: "bge-small", dimension: 384, multilingual: false, pinned: true, status: "ready" },
			],
			current: { provider: "fastembed", model: "BAAI/bge-small-en-v1.5" },
		},
		rerank: {
			label: "Reranker",
			kind: "curated",
			entries: [{ provider: "fastembed", id: "Xenova/ms-marco-MiniLM-L-6-v2", label: "MiniLM L6", pinned: true, status: "ready" }],
			current: { provider: "fastembed", model: "Xenova/ms-marco-MiniLM-L-6-v2", enabled: true, candidate_k: 24 },
		},
		vector_store: { label: "Vector store", kind: "curated", entries: [], current: { provider: "qdrant" } },
		compute: {
			label: "Compute device",
			kind: "curated",
			entries: [
				{ provider: "local", id: "cpu", label: "CPU", pinned: true, status: "ready" },
				{ provider: "local", id: "gpu", label: gpuStatus === "ready" ? "GPU (DirectML)" : "GPU", pinned: false, status: gpuStatus },
			],
			current: { device: "cpu" },
		},
	};
}

function renderPanel(gpuStatus: "ready" | "installable"): void {
	// ? Async mock whose branches all return thenables: satisfies require-await's
	// ? promise-return carve-out and promise-function-async at the same time
	mocks.get.mockImplementation(async (path: string): Promise<unknown> => {
		if (path === "/api/settings") return Promise.resolve(SETTINGS);
		if (path === "/api/capabilities") return Promise.resolve(capabilities(gpuStatus));
		if (path === "/api/index/status")
			return Promise.resolve({ collection_name: "c", total_vectors: 1, indexed_files: 1, last_updated: null, status: "ready", task_id: null });
		throw new Error(`unexpected ${path}`);
	});
	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	render(
		<QueryClientProvider client={client}>
			<SettingsPanel />
		</QueryClientProvider>
	);
}

describe("hardware toggle", () => {
	it("is disabled with a reason when the GPU runtime is not installed", async () => {
		renderPanel("installable");
		const toggle = await screen.findByLabelText(/use gpu for local models/i);
		expect(toggle).toBeDisabled();
		expect(screen.getByText(/gpu support not installed/i)).toBeInTheDocument();
	});

	it("is enabled and labeled with the backend when ready", async () => {
		renderPanel("ready");
		const toggle = await screen.findByLabelText(/use gpu for local models/i);
		expect(toggle).toBeEnabled();
		expect(screen.getByText(/GPU \(DirectML\)/)).toBeInTheDocument();
	});
});

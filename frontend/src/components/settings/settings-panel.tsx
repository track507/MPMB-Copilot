import { useCallback, useMemo, useState, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { INDEX_KEY, useSettings, useUpdateSettings, useIndexStatus, useTriggerIndex, useIndexTask, useCapabilities } from "@/hooks/use-settings";
import { ModelSelect } from "@/components/settings/model-select";
import { RerankSelect } from "@/components/settings/rerank-select";
import { cn } from "@/lib/utils";
import type { ChangeEvent, ReactElement } from "react";
import type { CapabilityEnvelope, ModelOption, Settings } from "@/types/settings";
import { classifyIndexResponse, isIndexBusy } from "@/lib/index-actions";
import {
	AlertDialog,
	AlertDialogAction,
	AlertDialogCancel,
	AlertDialogContent,
	AlertDialogDescription,
	AlertDialogFooter,
	AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const settingsSchema = z.object({
	default_llm_provider: z.string().min(1),
	default_model: z.string().min(1),
	temperature: z.number().min(0).max(2),
	max_tokens: z.number().int().min(1).max(32000),
	default_effort: z.string(),
	embedding_provider: z.string(),
	embedding_model: z.string(),
	anthropic_cheap_model: z.string(),
	openai_cheap_model: z.string(),
	ollama_cheap_model: z.string(),
	default_edition: z.string(),
	top_k_results: z.number().int().min(1).max(50),
	similarity_threshold: z.number().min(0).max(1),
	retrieval_mode: z.enum(["single", "dual", "auto"]),
	rerank_enabled: z.boolean(),
	rerank_provider: z.string(),
	rerank_model: z.string(),
	rerank_candidate_k: z.number().int().min(1).max(200),
	enable_tool_use: z.boolean(),
	enable_extended_thinking: z.boolean(),
	inference_device: z.enum(["cpu", "gpu"]),
});

type SettingsFormData = z.infer<typeof settingsSchema>;

const PROVIDERS = [
	{ value: "anthropic", label: "Anthropic" },
	{ value: "openai", label: "OpenAI" },
	{ value: "ollama", label: "Ollama (Local)" },
] as const;

const EDITIONS = [
	{ value: "2014", label: "D&D 2014" },
	{ value: "2024", label: "D&D 2024" },
] as const;

// Keep the selected effort valid for the current model's advertised levels (data-driven, no hardcoded list)
// Prefers the current value, then "high" (both providers expose it), then the highest available
function clampEffort(current: string, levels: readonly string[]): string {
	if (levels.length === 0 || levels.includes(current)) return current;
	if (levels.includes("high")) return "high";
	return levels[levels.length - 1] ?? current;
}

function titleCase(value: string): string {
	return value.charAt(0).toUpperCase() + value.slice(1);
}

function FieldLabel({ label, description }: { readonly label: string; readonly description?: string }): ReactElement {
	// ? Always render the description line (blank when absent) so paired grid cells stay the same height and their inputs align
	return (
		<div>
			<span className="text-sm font-medium">{label}</span>
			<p className="text-xs text-muted-foreground">{description ?? " "}</p>
		</div>
	);
}

export function SettingsPanel(): ReactElement {
	const settingsQuery = useSettings();
	const capabilitiesQuery = useCapabilities();

	// ? One paint: the form renders only when settings AND capabilities are ready, so sections never pop in
	if (settingsQuery.isError || capabilitiesQuery.isError) {
		return (
			<div className="flex flex-col items-center justify-center gap-3 py-12 text-sm text-muted-foreground">
				<p>Failed to load settings{capabilitiesQuery.isError ? " capabilities" : ""}.</p>
				<button
					type="button"
					onClick={() => {
						void settingsQuery.refetch();
						void capabilitiesQuery.refetch();
					}}
					className="rounded-md bg-secondary px-3 py-1.5 font-medium text-secondary-foreground hover:bg-secondary/80">
					Retry
				</button>
			</div>
		);
	}

	if (settingsQuery.data === undefined || capabilitiesQuery.data === undefined) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="size-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return <SettingsForm settings={settingsQuery.data} capabilities={capabilitiesQuery.data} />;
}

function SettingsForm({ settings, capabilities }: { readonly settings: Settings; readonly capabilities: CapabilityEnvelope }): ReactElement {
	const catalog = capabilities.generation.entries;
	// ! keep the {models, current} shape to accommodate for the current contract
	const embeddingCatalog = { models: capabilities.embedding.entries, current: capabilities.embedding.current };
	const rerank = capabilities.rerank;
	const updateSettings = useUpdateSettings();
	const { data: indexStatus } = useIndexStatus();
	const triggerIndex = useTriggerIndex();
	const queryClient = useQueryClient();
	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");

	// RHF's `values` keeps the form synced to server state (and resets dirty after each save)
	// settings is guaranteed defined here, so values never falls back to undefined
	const values = useMemo<SettingsFormData>(
		() => ({
			default_llm_provider: settings.default_llm_provider,
			default_model: settings.default_model,
			temperature: settings.temperature,
			max_tokens: settings.max_tokens,
			default_effort: settings.default_effort,
			embedding_provider: settings.embedding_provider,
			embedding_model: settings.embedding_model,
			anthropic_cheap_model: settings.anthropic_cheap_model,
			openai_cheap_model: settings.openai_cheap_model,
			ollama_cheap_model: settings.ollama_cheap_model,
			default_edition: settings.default_edition,
			top_k_results: settings.top_k_results,
			similarity_threshold: settings.similarity_threshold,
			retrieval_mode: settings.retrieval_mode,
			rerank_enabled: settings.rerank_enabled,
			rerank_provider: settings.rerank_provider,
			rerank_model: settings.rerank_model,
			rerank_candidate_k: settings.rerank_candidate_k,
			enable_tool_use: settings.enable_tool_use,
			enable_extended_thinking: settings.enable_extended_thinking,
			inference_device: settings.inference_device,
		}),
		[settings]
	);

	const {
		register,
		handleSubmit,
		control,
		getValues,
		setValue,
		formState: { isDirty },
	} = useForm<SettingsFormData>({
		resolver: zodResolver(settingsSchema),
		values,
	});

	// * Reactive reads via useWatch (Compiler-compatible, unlike watch())
	// All lists come from the backend catalog
	const provider = useWatch({ control, name: "default_llm_provider" });
	const model = useWatch({ control, name: "default_model" });
	const effort = useWatch({ control, name: "default_effort" });
	const anthropicCheap = useWatch({ control, name: "anthropic_cheap_model" });
	const openaiCheap = useWatch({ control, name: "openai_cheap_model" });
	const embeddingModel = useWatch({ control, name: "embedding_model" });
	const rerankModel = useWatch({ control, name: "rerank_model" });
	const embeddingChanged = embeddingCatalog.current.model !== embeddingModel;
	const compute = capabilities.compute;
	const gpuEntry = compute.entries.find((e) => e.id === "gpu");
	const gpuReady = gpuEntry?.status === "ready";
	const inferenceDevice = useWatch({ control, name: "inference_device" });
	const gpuActive = inferenceDevice === "gpu" && gpuReady;

	// ? Remember the last model chosen per provider so switching providers restores the right one (Ollama keeps its own id, not Anthropic's)
	const [lastModelByProvider, setLastModelByProvider] = useState<Record<string, string>>({
		[settings.default_llm_provider]: settings.default_model,
	});

	const optionsByProvider = useCallback(
		(prov: string): readonly ModelOption[] => {
			if (prov === "anthropic") return catalog.anthropic;
			if (prov === "openai") return catalog.openai;
			if (prov === "ollama") return catalog.ollama;
			return [];
		},
		[catalog]
	);

	const providerOptions = useMemo(() => optionsByProvider(provider), [optionsByProvider, provider]);
	const effortLevels = useMemo(() => providerOptions.find((o) => o.id === model)?.effort ?? [], [providerOptions, model]);

	const handleProviderChange = useCallback(
		(e: ChangeEvent<HTMLSelectElement>) => {
			const nextProvider = e.target.value;
			const opts = optionsByProvider(nextProvider);
			// Restore the last model used for this provider, else the first curated option, else blank (Ollama with no history)
			const nextModel = lastModelByProvider[nextProvider] ?? opts[0]?.id ?? "";
			setValue("default_model", nextModel, { shouldDirty: true, shouldValidate: true });
			const levels = opts.find((o) => o.id === nextModel)?.effort ?? [];
			setValue("default_effort", clampEffort(getValues("default_effort"), levels), { shouldDirty: true });
		},
		[optionsByProvider, setValue, getValues, lastModelByProvider]
	);

	const handleModelChange = useCallback(
		(next: string) => {
			setLastModelByProvider((prev) => ({ ...prev, [getValues("default_llm_provider")]: next }));
			setValue("default_model", next, { shouldDirty: true, shouldValidate: true });
			const levels = providerOptions.find((o) => o.id === next)?.effort ?? [];
			setValue("default_effort", clampEffort(getValues("default_effort"), levels), { shouldDirty: true });
		},
		[providerOptions, setValue, getValues]
	);

	const onSubmit = useCallback(
		(data: SettingsFormData) => {
			updateSettings.mutate(data, {
				onSuccess: () => {
					toast.success("Settings saved");
				},
				onError: () => {
					toast.error("Failed to save settings");
				},
			});
		},
		[updateSettings]
	);

	const [forceRebuild, setForceRebuild] = useState(false);
	const [confirmOpen, setConfirmOpen] = useState(false);
	const [startedTaskId, setStartedTaskId] = useState<string | null>(null);
	// ? Live status wins (covers CLI-started runs); startedTaskId only bridges the gap until the next status refetch
	const activeTaskId = indexStatus?.task_id ?? startedTaskId;
	const { data: activeTask } = useIndexTask(activeTaskId);
	const busy = isIndexBusy(indexStatus, activeTask) || triggerIndex.isPending;

	// ? One-shot per task id: toast + refresh exactly once when a run reaches a terminal state
	// No setState in here (react-hooks/set-state-in-effect): startedTaskId is never cleared - staleness is
	// harmless because polling stops on terminal status and status-first precedence shadows stale ids
	const handledTaskRef = useRef<string | null>(null);
	useEffect(() => {
		if (activeTaskId === null || activeTask === undefined) return;
		if (activeTask.status === "pending" || activeTask.status === "running") return;
		if (handledTaskRef.current === activeTaskId) return;
		handledTaskRef.current = activeTaskId;
		if (activeTask.status === "completed") toast.success("Indexing finished");
		if (activeTask.status === "failed") toast.error(activeTask.error ?? "Indexing failed");
		void queryClient.invalidateQueries({ queryKey: INDEX_KEY });
	}, [activeTask, activeTaskId, queryClient]);

	const runIndex = useCallback(() => {
		triggerIndex.mutate(
			{ force: forceRebuild },
			{
				onSuccess: (resp) => {
					const action = classifyIndexResponse(resp);
					if (action.kind === "started") {
						setStartedTaskId(action.taskId);
						toast.success("Indexing started");
					} else {
						// ? The honest no-op: surface the backend's own message
						toast.info(action.message);
					}
				},
				onError: () => {
					toast.error("Failed to start indexing");
				},
			}
		);
	}, [triggerIndex, forceRebuild]);

	const handleReindexClick = useCallback(() => {
		if (forceRebuild) {
			setConfirmOpen(true);
		} else {
			runIndex();
		}
	}, [forceRebuild, runIndex]);

	return (
		<form
			onSubmit={(e) => {
				void handleSubmit(onSubmit)(e);
			}}
			className="space-y-8">
			{/* LLM Configuration */}
			<section className="space-y-4">
				<h2 className="text-lg font-semibold">LLM Configuration</h2>

				<div className="grid gap-4 sm:grid-cols-2">
					<div className="space-y-2">
						<FieldLabel label="Provider" />
						<select {...register("default_llm_provider", { onChange: handleProviderChange })} className={inputClass}>
							{PROVIDERS.map((p) => (
								<option key={p.value} value={p.value}>
									{p.label}
								</option>
							))}
						</select>
					</div>

					<div className="space-y-2">
						<FieldLabel label="Model" description="Pick from the provider's models or choose Custom..." />
						<ModelSelect value={model} onChange={handleModelChange} options={providerOptions} placeholder="Enter model id" />
					</div>

					<div className="space-y-2">
						<FieldLabel label="Temperature" description="0 = deterministic, 2 = creative" />
						<input {...register("temperature", { valueAsNumber: true })} type="number" step="0.1" min="0" max="2" className={inputClass} />
					</div>

					<div className="space-y-2">
						<FieldLabel label="Max Tokens" />
						<input {...register("max_tokens", { valueAsNumber: true })} type="number" min="1" max="32000" className={inputClass} />
					</div>

					{effortLevels.length > 0 && (
						<div className="space-y-2">
							<FieldLabel label="Reasoning effort" description="Deeper reasoning uses more tokens" />
							<select
								value={clampEffort(effort, effortLevels)}
								onChange={(e) => {
									setValue("default_effort", e.target.value, { shouldDirty: true });
								}}
								className={inputClass}>
								{effortLevels.map((level) => (
									<option key={level} value={level}>
										{titleCase(level)}
									</option>
								))}
							</select>
						</div>
					)}
				</div>

				<div className="flex items-center gap-3">
					<input {...register("enable_extended_thinking")} type="checkbox" id="extended-thinking" className="size-4 rounded" />
					<label htmlFor="extended-thinking" className="text-sm">
						Enable extended thinking (Anthropic only)
					</label>
				</div>

				<div className="flex items-center gap-3">
					<input {...register("enable_tool_use")} type="checkbox" id="tool-use" className="size-4 rounded" />
					<label htmlFor="tool-use" className="text-sm">
						Enable tool use
					</label>
				</div>

				<div className="space-y-3">
					<FieldLabel label="Cheap models" description="Lighter models for auxiliary tasks like title generation. Used per provider." />
					<div className="grid gap-4 sm:grid-cols-3">
						<div className="space-y-2">
							<span className="text-xs text-muted-foreground">Anthropic</span>
							<ModelSelect
								value={anthropicCheap}
								onChange={(v) => {
									setValue("anthropic_cheap_model", v, { shouldDirty: true });
								}}
								options={optionsByProvider("anthropic")}
								placeholder="claude-haiku-4-5"
							/>
						</div>
						<div className="space-y-2">
							<span className="text-xs text-muted-foreground">OpenAI</span>
							<ModelSelect
								value={openaiCheap}
								onChange={(v) => {
									setValue("openai_cheap_model", v, { shouldDirty: true });
								}}
								options={optionsByProvider("openai")}
								placeholder="gpt-5.4-mini"
							/>
						</div>
						<div className="space-y-2">
							<span className="text-xs text-muted-foreground">Ollama</span>
							<input {...register("ollama_cheap_model")} className={inputClass} placeholder="(falls back to model)" />
						</div>
					</div>
				</div>
			</section>

			{/* RAG Configuration */}
			<section className="space-y-4">
				<h2 className="text-lg font-semibold">Retrieval Configuration</h2>

				<div className="grid gap-4 sm:grid-cols-2">
					<div className="space-y-2">
						<FieldLabel label="Default Edition" />
						<select {...register("default_edition")} className={inputClass}>
							{EDITIONS.map((e) => (
								<option key={e.value} value={e.value}>
									{e.label}
								</option>
							))}
						</select>
					</div>

					<div className="space-y-2">
						<FieldLabel label="Retrieval Mode" />
						<select {...register("retrieval_mode")} className={inputClass}>
							<option value="single">Single search</option>
							<option value="dual">Dual search (authoritative + examples)</option>
							<option value="auto">Auto</option>
						</select>
					</div>

					<div className="space-y-2">
						<FieldLabel label="Top K Results" description="Chunks retrieved per query" />
						<input {...register("top_k_results", { valueAsNumber: true })} type="number" min="1" max="50" className={inputClass} />
					</div>

					<div className="space-y-2">
						<FieldLabel label="Similarity Threshold" description="Minimum score to include a chunk" />
						<input
							{...register("similarity_threshold", { valueAsNumber: true })}
							type="number"
							step="0.05"
							min="0"
							max="1"
							className={inputClass}
						/>
					</div>
				</div>
			</section>

			{/* Hardware */}
			<section className="space-y-4">
				<h2 className="text-lg font-semibold">{compute.label}</h2>
				<div className="flex items-center gap-3">
					<input
						type="checkbox"
						id="inference-device"
						checked={inferenceDevice === "gpu"}
						disabled={!gpuReady}
						onChange={(e) => {
							setValue("inference_device", e.target.checked ? "gpu" : "cpu", { shouldDirty: true });
						}}
						className="size-4 rounded"
					/>
					<label htmlFor="inference-device" className="text-sm">
						Use GPU for local models{gpuEntry && gpuReady ? ` - ${gpuEntry.label}` : ""}
						<span className="block text-xs text-muted-foreground">
							{gpuReady
								? "Applies to locally-run models (embedding, reranking); cloud providers are unaffected"
								: "GPU support not installed on this backend"}
						</span>
					</label>
				</div>
			</section>

			{/* Reranker */}
			<section className="space-y-4">
				<h2 className="text-lg font-semibold">
					{rerank.label}
					{gpuActive && (
						<span className="ml-2 rounded bg-secondary px-1.5 py-0.5 align-middle text-xs font-medium text-secondary-foreground">GPU</span>
					)}
				</h2>
				<div className="flex items-center gap-3">
					<input {...register("rerank_enabled")} type="checkbox" id="rerank-enabled" className="size-4 rounded" />
					<label htmlFor="rerank-enabled" className="text-sm">
						Rerank search results (cross-encoder over hybrid candidates)
					</label>
				</div>
				<div className="grid gap-4 sm:grid-cols-2">
					<div className="space-y-2">
						<FieldLabel label="Reranker model" description="Re-scores candidates before the budget cut" />
						<RerankSelect
							value={rerankModel}
							options={rerank.entries}
							onChange={(prov, id) => {
								setValue("rerank_provider", prov, { shouldDirty: true });
								setValue("rerank_model", id, { shouldDirty: true });
							}}
						/>
					</div>
					<div className="space-y-2">
						<FieldLabel label="Candidate pool" description="Candidates scored per tier before the cut" />
						<input {...register("rerank_candidate_k", { valueAsNumber: true })} type="number" min="1" max="200" className={inputClass} />
					</div>
				</div>
			</section>

			{/* Index Status */}
			<section className="space-y-4">
				<h2 className="text-lg font-semibold">Vector Index</h2>
				<div className="rounded-md border border-border p-4 text-sm">
					<div className="grid grid-cols-2 gap-2">
						<span className="text-muted-foreground">Status</span>
						<span className="font-medium">{indexStatus?.status ?? "unknown"}</span>
						<span className="text-muted-foreground">Vectors</span>
						<span className="font-medium">{String(indexStatus?.total_vectors ?? 0)}</span>
						<span className="text-muted-foreground">Files indexed</span>
						<span className="font-medium">{String(indexStatus?.indexed_files ?? 0)}</span>
					</div>

					{activeTask !== undefined && (activeTask.status === "pending" || activeTask.status === "running") && (
						<div className="mt-3 space-y-1">
							<div className="h-2 w-full overflow-hidden rounded-full bg-muted">
								<div
									className="h-full bg-primary transition-all"
									style={{ width: `${String(Math.round((activeTask.progress ?? 0) * 100))}%` }}
								/>
							</div>
							<p className="text-xs text-muted-foreground">{activeTask.progress_message ?? "Indexing..."}</p>
						</div>
					)}

					<button
						type="button"
						onClick={handleReindexClick}
						disabled={busy}
						className="mt-3 rounded-md bg-secondary px-3 py-1.5 text-sm font-medium text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50">
						{busy ? "Indexing..." : "Re-index"}
					</button>

					<div className="mt-3 flex items-center gap-3">
						<input
							type="checkbox"
							id="force-rebuild"
							checked={forceRebuild}
							onChange={(e) => {
								setForceRebuild(e.target.checked);
							}}
							className="size-4 rounded"
						/>
						<label htmlFor="force-rebuild" className="text-sm">
							Force rebuild
							<span className="block text-xs text-muted-foreground">
								Drops the index and rebuilds all vectors; required after changing the embedding model
							</span>
						</label>
					</div>
				</div>

				<AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
					<AlertDialogContent>
						<AlertDialogTitle>Rebuild the index from scratch?</AlertDialogTitle>
						<AlertDialogDescription>
							This drops all {String(indexStatus?.total_vectors ?? 0)} vectors and re-embeds everything. Search is degraded until it finishes.
						</AlertDialogDescription>
						<AlertDialogFooter>
							<AlertDialogCancel>Cancel</AlertDialogCancel>
							<AlertDialogAction onClick={runIndex}>Rebuild</AlertDialogAction>
						</AlertDialogFooter>
					</AlertDialogContent>
				</AlertDialog>

				<div className="space-y-2">
					<FieldLabel label="Embedding model" description="Builds and queries the vector index" />
					<select
						value={embeddingModel}
						onChange={(e) => {
							const next = embeddingCatalog.models.find((m) => m.id === e.target.value);
							if (next) {
								setValue("embedding_provider", next.provider, { shouldDirty: true });
								setValue("embedding_model", next.id, { shouldDirty: true });
							}
						}}
						className={inputClass}>
						{embeddingCatalog.models.map((m) => (
							<option key={`${m.provider}:${m.id}`} value={m.id} disabled={m.status !== "ready"}>
								{m.label} - {m.dimension}d{m.multilingual ? " - multilingual" : ""}
								{m.status === "needs_key" ? " (set API key)" : m.status === "installable" ? " (install via add-ons)" : ""}
							</option>
						))}
					</select>
					{embeddingChanged && (
						<p className="text-xs text-amber-600">
							Changing the embedding model requires a full rebuild: turn on Force rebuild above, then Re-index.
						</p>
					)}
				</div>
			</section>

			{/* Save */}
			<div className="flex justify-end">
				<button
					type="submit"
					disabled={!isDirty || updateSettings.isPending}
					className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50">
					{updateSettings.isPending ? "Saving..." : "Save Settings"}
				</button>
			</div>
		</form>
	);
}

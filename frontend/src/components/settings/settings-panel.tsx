import { useCallback, useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useSettings, useUpdateSettings, useIndexStatus, useTriggerIndex, useModelCatalog, useEmbeddingCatalog } from "@/hooks/use-settings";
import { ModelSelect } from "@/components/settings/model-select";
import { cn } from "@/lib/utils";
import type { ChangeEvent, ReactElement } from "react";
import type { ModelOption, Settings } from "@/types/settings";

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
	enable_tool_use: z.boolean(),
	enable_extended_thinking: z.boolean(),
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
	const { data: settings, isLoading } = useSettings();

	// Gate on load so the inner form always has defined settings - lets `values` stay non-optional
	if (isLoading || settings === undefined) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="size-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	return <SettingsForm settings={settings} />;
}

function SettingsForm({ settings }: { readonly settings: Settings }): ReactElement {
	const { data: catalog } = useModelCatalog();
	const { data: embeddingCatalog } = useEmbeddingCatalog();
	const updateSettings = useUpdateSettings();
	const { data: indexStatus } = useIndexStatus();
	const triggerIndex = useTriggerIndex();
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
			enable_tool_use: settings.enable_tool_use,
			enable_extended_thinking: settings.enable_extended_thinking,
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
	const embeddingChanged = embeddingCatalog !== undefined && embeddingCatalog.current.model !== embeddingModel;

	// ? Remember the last model chosen per provider so switching providers restores the right one (Ollama keeps its own id, not Anthropic's)
	const [lastModelByProvider, setLastModelByProvider] = useState<Record<string, string>>({
		[settings.default_llm_provider]: settings.default_model,
	});

	const optionsByProvider = useCallback(
		(prov: string): readonly ModelOption[] => {
			if (catalog === undefined) return [];
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

	const handleReindex = useCallback(() => {
		triggerIndex.mutate(undefined, {
			onSuccess: () => {
				toast.success("Indexing started");
			},
			onError: () => {
				toast.error("Failed to start indexing");
			},
		});
	}, [triggerIndex]);

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
					<button
						type="button"
						onClick={handleReindex}
						disabled={triggerIndex.isPending}
						className="mt-3 rounded-md bg-secondary px-3 py-1.5 text-sm font-medium text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50">
						{triggerIndex.isPending ? "Starting..." : "Re-index"}
					</button>
				</div>

				{embeddingCatalog && (
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
							<p className="text-xs text-amber-600">Changing the embedding model requires a full re-index (use Re-index above).</p>
						)}
					</div>
				)}
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

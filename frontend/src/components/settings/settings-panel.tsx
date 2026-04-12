import { useCallback, useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { useSettings, useUpdateSettings, useIndexStatus, useTriggerIndex } from "@/hooks/use-settings";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

const settingsSchema = z.object({
	default_llm_provider: z.string().min(1),
	default_model: z.string().min(1),
	temperature: z.number().min(0).max(2),
	max_tokens: z.number().int().min(1).max(8000),
	default_edition: z.string(),
	top_k_results: z.number().int().min(1).max(50),
	similarity_threshold: z.number().min(0).max(1),
	retrieval_mode: z.enum(["single", "dual", "auto"]),
	enable_tool_use: z.boolean(),
	enable_extended_thinking: z.boolean(),
	thinking_budget_tokens: z.number().int().min(1000).max(32000),
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

function FieldLabel({ label, description }: { readonly label: string; readonly description?: string }): ReactElement {
	return (
		<div>
			<span className="text-sm font-medium">{label}</span>
			{description !== undefined && <p className="text-xs text-muted-foreground">{description}</p>}
		</div>
	);
}

export function SettingsPanel(): ReactElement {
	const { data: settings, isLoading } = useSettings();
	const updateSettings = useUpdateSettings();
	const { data: indexStatus } = useIndexStatus();
	const triggerIndex = useTriggerIndex();

	const {
		register,
		handleSubmit,
		reset,
		formState: { isDirty },
	} = useForm<SettingsFormData>({
		resolver: zodResolver(settingsSchema),
	});

	// Populate form when settings load
	useEffect(() => {
		if (settings !== undefined) {
			reset({
				default_llm_provider: settings.default_llm_provider,
				default_model: settings.default_model,
				temperature: settings.temperature,
				max_tokens: settings.max_tokens,
				default_edition: settings.default_edition,
				top_k_results: settings.top_k_results,
				similarity_threshold: settings.similarity_threshold,
				retrieval_mode: settings.retrieval_mode,
				enable_tool_use: settings.enable_tool_use,
				enable_extended_thinking: settings.enable_extended_thinking,
				thinking_budget_tokens: settings.thinking_budget_tokens,
			});
		}
	}, [settings, reset]);

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

	if (isLoading) {
		return (
			<div className="flex items-center justify-center py-12">
				<Loader2 className="size-6 animate-spin text-muted-foreground" />
			</div>
		);
	}

	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");

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
						<select {...register("default_llm_provider")} className={inputClass}>
							{PROVIDERS.map((p) => (
								<option key={p.value} value={p.value}>
									{p.label}
								</option>
							))}
						</select>
					</div>

					<div className="space-y-2">
						<FieldLabel label="Model" description="Provider-specific model identifier" />
						<input {...register("default_model")} className={inputClass} />
					</div>

					<div className="space-y-2">
						<FieldLabel label="Temperature" description="0 = deterministic, 2 = creative" />
						<input {...register("temperature", { valueAsNumber: true })} type="number" step="0.1" min="0" max="2" className={inputClass} />
					</div>

					<div className="space-y-2">
						<FieldLabel label="Max Tokens" />
						<input {...register("max_tokens", { valueAsNumber: true })} type="number" min="1" max="8000" className={inputClass} />
					</div>
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

import { useState } from "react";
import type { ReactElement } from "react";
import { cn } from "@/lib/utils";
import type { ModelOption } from "@/types/settings";

const CUSTOM = "__custom__";

interface ModelSelectProps {
	readonly value: string;
	readonly onChange: (value: string) => void;
	readonly options: readonly ModelOption[];
	readonly id?: string;
	readonly placeholder?: string;
}

/**
 * Model picker driven entirely by the backend catalog - no hardcoded lists.
 * Shows the provider's known models plus a "Custom..." escape hatch for typing an
 * arbitrary id. When the provider exposes no curated models (e.g. Ollama, or the
 * catalog is still loading) it degrades to a plain free-form input.
 */
export function ModelSelect({ value, onChange, options, id, placeholder }: ModelSelectProps): ReactElement {
	const [customMode, setCustomMode] = useState(false);
	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");

	if (options.length === 0) {
		return (
			<input
				id={id}
				value={value}
				onChange={(e) => {
					onChange(e.target.value);
				}}
				placeholder={placeholder}
				className={inputClass}
			/>
		);
	}

	const isKnown = options.some((o) => o.id === value);
	const showCustom = customMode || !isKnown;

	return (
		<div className="space-y-2">
			<select
				id={id}
				value={showCustom ? CUSTOM : value}
				onChange={(e) => {
					if (e.target.value === CUSTOM) {
						setCustomMode(true);
					} else {
						setCustomMode(false);
						onChange(e.target.value);
					}
				}}
				className={inputClass}>
				{options.map((o) => (
					<option key={o.id} value={o.id}>
						{o.label}
					</option>
				))}
				<option value={CUSTOM}>Custom...</option>
			</select>
			{showCustom && (
				<input
					value={value}
					onChange={(e) => {
						onChange(e.target.value);
					}}
					placeholder={placeholder ?? "Enter model id"}
					className={inputClass}
				/>
			)}
		</div>
	);
}

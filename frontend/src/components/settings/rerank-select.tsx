import type { ReactElement } from "react";
import { cn } from "@/lib/utils";
import type { RerankModelOption } from "@/types/settings";

interface RerankSelectProps {
	readonly value: string;
	readonly options: readonly RerankModelOption[];
	readonly onChange: (provider: string, id: string) => void;
}

/**
 * Reranker picker driven by the capabilities envelope. Non-ready entries (needs_key / installable) are shown but disabled, matching the embedding picker idiom
 */
export function RerankSelect({ value, options, onChange }: RerankSelectProps): ReactElement {
	const inputClass = cn("w-full rounded-md border border-input bg-background px-3 py-2 text-sm", "focus:outline-none focus:ring-2 focus:ring-ring");
	return (
		<select
			value={value}
			onChange={(e) => {
				const next = options.find((o) => o.id === e.target.value);
				if (next) onChange(next.provider, next.id);
			}}
			className={inputClass}>
			{options.map((o) => (
				<option key={`${o.provider}:${o.id}`} value={o.id} disabled={o.status !== "ready"}>
					{o.label}
					{o.status === "needs_key" ? " (set API key)" : o.status === "installable" ? " (install via add-ons)" : ""}
				</option>
			))}
		</select>
	);
}

import { ChevronDown, FileCode } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";
import type { SourceReference } from "@/types/chat";

interface SourceCitationProps {
	readonly sources: SourceReference[];
}

export function SourceCitation({ sources }: SourceCitationProps): ReactElement {
	const [expanded, setExpanded] = useState(false);

	return (
		<div className="rounded-md border border-border text-left">
			<button
				type="button"
				onClick={() => {
					setExpanded((prev) => !prev);
				}}
				className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-muted/50">
				<FileCode className="size-3.5" />
				<span>
					{String(sources.length)} source{sources.length !== 1 ? "s" : ""} referenced
				</span>
				<ChevronDown className={cn("ml-auto size-3.5 transition-transform", expanded && "rotate-180")} />
			</button>

			{expanded && (
				<div className="border-t border-border">
					{sources.map((source, i) => (
						<div key={i} className="border-b border-border p-3 last:border-b-0">
							<div className="mb-1 flex items-center justify-between">
								<span className="text-xs font-medium">{source.file}</span>
								<span className="text-xs text-muted-foreground">{(source.score * 100).toFixed(0)}% match</span>
							</div>
							{source.line_range !== undefined && (
								<span className="text-xs text-muted-foreground">
									Lines {String(source.line_range[0])}-{String(source.line_range[1])}
								</span>
							)}
							<pre className="mt-1 overflow-x-auto rounded bg-muted/50 p-2 text-xs">{source.content}</pre>
						</div>
					))}
				</div>
			)}
		</div>
	);
}

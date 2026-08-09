import { FileText, Loader2, X } from "lucide-react";
import { useUploadStore } from "@/stores/upload-store";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";

function formatSize(bytes: number): string {
	if (bytes < 1024) return `${String(bytes)} B`;
	if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function AttachmentChips(): ReactElement | null {
	const staged = useUploadStore((s) => s.staged);
	const removeStaged = useUploadStore((s) => s.removeStaged);

	if (staged.length === 0) return null;

	return (
		<div className="mb-2 flex flex-wrap gap-2">
			{staged.map((att) => (
				<div
					key={att.id}
					className={cn(
						"inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs",
						att.status === "error" ? "border-destructive text-destructive" : "border-border text-foreground"
					)}
					title={att.status === "error" ? att.error : undefined}>
					{att.status === "uploading" ? <Loader2 className="size-3.5 animate-spin" /> : <FileText className="size-3.5" />}
					<span className="max-w-48 truncate">{att.file.name}</span>
					<span className="text-muted-foreground">
						{att.status === "uploading" ? `${String(Math.round(att.progress * 100))}%` : formatSize(att.file.size)}
					</span>
					{att.file.name.toLowerCase().endsWith(".pdf") && <span className="text-muted-foreground">(stored, not yet readable by the assistant)</span>}
					<button
						type="button"
						onClick={() => {
							removeStaged(att.id);
						}}
						aria-label={`Remove ${att.file.name}`}
						className="text-muted-foreground transition-colors hover:text-foreground">
						<X className="size-3.5" />
					</button>
				</div>
			))}
		</div>
	);
}

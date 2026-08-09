import { useRef, useState } from "react";
import { Download, FileText, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { useIsAdmin } from "@/hooks/use-auth";
import { uploadFile } from "@/lib/http";
import { useDeleteUpload, useLibraryFiles, uploadContentUrl } from "@/lib/uploads";
import { UPLOAD_EXTENSIONS } from "@/stores/upload-store";
import { cn } from "@/lib/utils";
import type { FileOut } from "@/types/uploads";
import type { ReactElement } from "react";

type LibraryTab = "global" | "shared";

function formatSize(bytes: number): string {
	if (bytes < 1024) return `${String(bytes)} B`;
	if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

function formatDate(iso: string): string {
	return Temporal.Instant.from(iso)
		.toZonedDateTimeISO(Temporal.Now.timeZoneId())
		.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export default function LibraryPage(): ReactElement {
	const [tab, setTab] = useState<LibraryTab>("global");
	const [uploading, setUploading] = useState(false);
	const fileInputRef = useRef<HTMLInputElement>(null);
	const { isAdmin } = useIsAdmin();
	const { data, refetch } = useLibraryFiles(tab);
	const deleteUpload = useDeleteUpload();

	// * Shared is admin-managed; a user's own library is always writable
	const canWrite = tab === "global" || isAdmin;
	const files = data?.files ?? [];

	const handlePicked = async (picked: FileList | null): Promise<void> => {
		if (picked === null || picked.length === 0) return;
		setUploading(true);
		try {
			for (const file of [...picked]) {
				try {
					// * Library uploads are upload-on-pick: the pick IS the deliberate action, no staging
					await uploadFile<FileOut>("/api/uploads", file, { scope: tab });
				} catch (err) {
					toast.error(err instanceof Error ? err.message : `Failed to upload ${file.name}`);
				}
			}
			await refetch();
		} finally {
			setUploading(false);
		}
	};

	const handleDelete = (file: FileOut): void => {
		deleteUpload.mutate(file.id, {
			onError: () => {
				toast.error(`Failed to remove ${file.filename}`);
			},
		});
	};

	return (
		<div className="mx-auto max-w-2xl px-4 py-8">
			<h1 className="text-2xl font-bold tracking-tight">Library</h1>
			<p className="mt-1 text-sm text-muted-foreground">Files the assistant can read across your chats.</p>

			<div className="mt-6 flex gap-1 border-b border-border">
				{(["global", "shared"] as const).map((t) => (
					<button
						key={t}
						type="button"
						onClick={() => {
							setTab(t);
						}}
						className={cn(
							"px-4 py-2 text-sm font-medium transition-colors",
							tab === t ? "-mb-px border-b-2 border-primary text-foreground" : "text-muted-foreground hover:text-foreground"
						)}>
						{t === "global" ? "My library" : "Shared"}
					</button>
				))}
			</div>

			{canWrite ? (
				<div className="mt-4">
					<input
						ref={fileInputRef}
						type="file"
						multiple
						accept={UPLOAD_EXTENSIONS.join(",")}
						className="hidden"
						onChange={(e) => {
							void handlePicked(e.target.files);
							e.target.value = "";
						}}
					/>
					<button
						type="button"
						onClick={() => {
							fileInputRef.current?.click();
						}}
						disabled={uploading}
						className="inline-flex items-center gap-2 rounded-lg border border-input px-3 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50">
						<Upload className="size-4" />
						{uploading ? "Uploading..." : "Upload files"}
					</button>
				</div>
			) : (
				<p className="mt-4 text-sm text-muted-foreground">The shared library is managed by admins.</p>
			)}

			<div className="mt-4 space-y-1">
				{files.length === 0 ? (
					<p className="py-8 text-center text-sm text-muted-foreground">No files yet.</p>
				) : (
					files.map((file) => (
						<div
							key={file.id}
							className={cn(
								"flex items-center gap-3 rounded-lg border px-3 py-2 text-sm",
								file.missing ? "border-destructive/50" : "border-border"
							)}>
							<FileText className="size-4 shrink-0 text-muted-foreground" />
							<div className="min-w-0 flex-1">
								<div className="truncate font-medium">{file.filename}</div>
								<div className="text-xs text-muted-foreground">
									{formatSize(file.file_size)} - {formatDate(file.uploaded_at)}
									{file.missing && <span className="text-destructive"> - missing on disk</span>}
									{file.filename.toLowerCase().endsWith(".pdf") && <span> - not yet readable</span>}
								</div>
							</div>
							<a
								href={uploadContentUrl(file.id)}
								download={file.filename}
								title="Download"
								className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:text-foreground">
								<Download className="size-4" />
							</a>
							{canWrite && (
								<button
									type="button"
									onClick={() => {
										handleDelete(file);
									}}
									title="Remove"
									className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:text-destructive">
									<Trash2 className="size-4" />
								</button>
							)}
						</div>
					))
				)}
			</div>
		</div>
	);
}

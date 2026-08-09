export type UploadScope = "session" | "global" | "shared";

export interface FileOut {
	readonly id: string;
	readonly scope: UploadScope;
	readonly session_id: string | null;
	readonly filename: string;
	readonly original_filename: string;
	readonly file_size: number;
	readonly content_type: string;
	readonly file_hash: string;
	readonly uploaded_at: string;
	readonly message_id: string | null;
	readonly missing: boolean;
}

export interface FileListOut {
	readonly files: readonly FileOut[];
	readonly total: number;
}

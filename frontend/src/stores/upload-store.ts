import { create } from "zustand";

export type StagedStatus = "staged" | "uploading" | "uploaded" | "error";

export interface StagedAttachment {
	readonly id: string;
	readonly file: File;
	readonly status: StagedStatus;
	readonly progress: number;
	readonly error?: string;
	readonly fileId?: string;
}

// Mirrors of the backend upload policy (sanitize.py / settings.py) for instant client-side feedback
export const UPLOAD_EXTENSIONS = [".js", ".txt", ".md", ".yml", ".yaml", ".json", ".pdf"] as const;
export const MAX_UPLOAD_BYTES = 52_428_800;
const MAX_STAGED_FILES = 10;

interface UploadStoreState {
	staged: readonly StagedAttachment[];
}

interface UploadStoreActions {
	stageFiles: (files: readonly File[]) => readonly string[];
	removeStaged: (id: string) => void;
	markUploading: (id: string) => void;
	setProgress: (id: string, progress: number) => void;
	markUploaded: (id: string, fileId: string) => void;
	markFailed: (id: string, error: string) => void;
	clearStaged: () => void;
}

type UploadStore = UploadStoreState & UploadStoreActions;

function hasAllowedExtension(name: string): boolean {
	const lower = name.toLowerCase();
	return UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

function patch(staged: readonly StagedAttachment[], id: string, changes: Partial<StagedAttachment>): readonly StagedAttachment[] {
	return staged.map((att) => (att.id === id ? { ...att, ...changes } : att));
}

export const useUploadStore = create<UploadStore>((set, get) => ({
	staged: [],

	stageFiles: (files) => {
		const rejections: string[] = [];
		const accepted: StagedAttachment[] = [];
		let count = get().staged.length;

		for (const file of files) {
			if (!hasAllowedExtension(file.name)) {
				rejections.push(`${file.name}: file type not supported`);
			} else if (file.size > MAX_UPLOAD_BYTES) {
				rejections.push(`${file.name}: larger than 50 MB`);
			} else if (file.size === 0) {
				rejections.push(`${file.name}: file is empty`);
			} else if (count >= MAX_STAGED_FILES) {
				rejections.push(`${file.name}: too many attachments`);
			} else {
				count += 1;
				accepted.push({ id: crypto.randomUUID(), file, status: "staged", progress: 0 });
			}
		}
		if (accepted.length > 0) {
			set((s) => ({ staged: [...s.staged, ...accepted] }));
		}
		return rejections;
	},

	removeStaged: (id) => {
		set((s) => ({ staged: s.staged.filter((att) => att.id !== id) }));
	},

	markUploading: (id) => {
		set((s) => ({ staged: patch(s.staged, id, { status: "uploading", progress: 0 }) }));
	},

	setProgress: (id, progress) => {
		set((s) => ({ staged: patch(s.staged, id, { progress }) }));
	},

	markUploaded: (id, fileId) => {
		set((s) => ({ staged: patch(s.staged, id, { status: "uploaded", progress: 1, fileId }) }));
	},

	markFailed: (id, error) => {
		set((s) => ({ staged: patch(s.staged, id, { status: "error", error }) }));
	},

	clearStaged: () => {
		set({ staged: [] });
	},
}));

import { beforeEach, describe, expect, it } from "vitest";

import { MAX_UPLOAD_BYTES, type StagedAttachment, useUploadStore } from "@/stores/upload-store";

function makeFile(name: string, size = 10): File {
	return new File([new ArrayBuffer(size)], name);
}

function first(): StagedAttachment {
	const [att] = useUploadStore.getState().staged;
	if (att === undefined) throw new Error("expected a staged attachment");
	return att;
}

beforeEach(() => {
	useUploadStore.getState().clearStaged();
});

describe("stageFiles", () => {
	it("accepts allowed files with no rejections", () => {
		const rejections = useUploadStore.getState().stageFiles([makeFile("a.js"), makeFile("notes.md")]);
		expect(rejections).toEqual([]);
		expect(useUploadStore.getState().staged).toHaveLength(2);
	});

	it("rejects a disallowed extension and stages nothing", () => {
		const rejections = useUploadStore.getState().stageFiles([makeFile("evil.exe")]);
		expect(rejections).toHaveLength(1);
		expect(rejections[0]).toContain("not supported");
		expect(useUploadStore.getState().staged).toHaveLength(0);
	});

	it("rejects a file over the 50 MB cap", () => {
		const rejections = useUploadStore.getState().stageFiles([makeFile("big.js", MAX_UPLOAD_BYTES + 1)]);
		expect(rejections[0]).toContain("50 MB");
		expect(useUploadStore.getState().staged).toHaveLength(0);
	});

	it("rejects an empty file", () => {
		const rejections = useUploadStore.getState().stageFiles([makeFile("empty.js", 0)]);
		expect(rejections[0]).toContain("empty");
	});

	it("caps the staged count at ten", () => {
		const many = Array.from({ length: 12 }, (_, i) => makeFile(`f${String(i)}.js`));
		const rejections = useUploadStore.getState().stageFiles(many);
		expect(useUploadStore.getState().staged).toHaveLength(10);
		expect(rejections).toHaveLength(2);
		expect(rejections[0]).toContain("too many");
	});
});

describe("lifecycle", () => {
	it("transitions staged -> uploading -> uploaded", () => {
		useUploadStore.getState().stageFiles([makeFile("a.js")]);
		const id = first().id;

		useUploadStore.getState().markUploading(id);
		expect(first().status).toBe("uploading");

		useUploadStore.getState().setProgress(id, 0.5);
		expect(first().progress).toBe(0.5);

		useUploadStore.getState().markUploaded(id, "file-123");
		expect(first().status).toBe("uploaded");
		expect(first().fileId).toBe("file-123");
		expect(first().progress).toBe(1);
	});

	it("markFailed marks one and leaves the others untouched", () => {
		useUploadStore.getState().stageFiles([makeFile("a.js"), makeFile("b.js")]);
		const [target, other] = useUploadStore.getState().staged;
		if (target === undefined || other === undefined) throw new Error("expected two staged");

		useUploadStore.getState().markFailed(target.id, "boom");

		const after = useUploadStore.getState().staged;
		expect(after.find((s) => s.id === target.id)?.status).toBe("error");
		expect(after.find((s) => s.id === target.id)?.error).toBe("boom");
		expect(after.find((s) => s.id === other.id)?.status).toBe("staged");
	});

	it("removeStaged drops one and clearStaged empties", () => {
		useUploadStore.getState().stageFiles([makeFile("a.js"), makeFile("b.js")]);
		useUploadStore.getState().removeStaged(first().id);
		expect(useUploadStore.getState().staged).toHaveLength(1);
		useUploadStore.getState().clearStaged();
		expect(useUploadStore.getState().staged).toHaveLength(0);
	});
});

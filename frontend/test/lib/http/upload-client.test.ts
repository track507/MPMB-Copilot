import { afterEach, expect, it, vi } from "vitest";

import { uploadFile } from "@/lib/http/upload-client";

class FakeXHR {
	status = 0;
	response: unknown = null;
	responseType = "";
	withCredentials = false;
	upload = { onprogress: null as ((e: ProgressEvent) => void) | null };
	onload: (() => void) | null = null;
	onerror: (() => void) | null = null;
	open = vi.fn();
	send = vi.fn(() => {
		this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 } as ProgressEvent);
		queueMicrotask(() => this.onload?.());
	});
}

afterEach(() => vi.unstubAllGlobals());

it("resolves with the parsed body and reports progress on 2xx", async () => {
	const xhr = new FakeXHR();
	xhr.status = 201;
	xhr.response = { id: "abc" };
	vi.stubGlobal(
		"XMLHttpRequest",
		vi.fn(function () {
			return xhr;
		})
	);
	const seen: number[] = [];
	const out = await uploadFile<{ id: string }>("/api/uploads", new File(["x"], "a.js"), { scope: "session" }, (f) => seen.push(f));
	expect(out).toEqual({ id: "abc" });
	expect(seen).toContain(0.5);
});

it("rejects with an ApiError carrying the problem on non-2xx", async () => {
	const xhr = new FakeXHR();
	xhr.status = 413;
	xhr.response = { type: "/api/problems/file-too-large", title: "File too large", status: 413, detail: "Too big." };
	vi.stubGlobal(
		"XMLHttpRequest",
		vi.fn(function () {
			return xhr;
		})
	);
	await expect(uploadFile("/api/uploads", new File(["x"], "a.js"), {})).rejects.toMatchObject({
		status: 413,
		problem: { type: "/api/problems/file-too-large" },
	});
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

// vi.mock is hoisted above the module body, so the mocks it references must be hoisted too
const { get, del } = vi.hoisted(() => ({ get: vi.fn(), del: vi.fn() }));
vi.mock("@/lib/http", () => ({ apiClient: { get, delete: del }, BASE_URL: "" }));

import { useDeleteUpload, useLibraryFiles, useSessionFiles, uploadContentUrl } from "@/lib/uploads";

function makeClient(): QueryClient {
	return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function makeWrapper(client: QueryClient) {
	return function Wrapper({ children }: { children: ReactNode }) {
		return createElement(QueryClientProvider, { client }, children);
	};
}

beforeEach(() => {
	get.mockReset().mockResolvedValue({ files: [], total: 0 });
	del.mockReset().mockResolvedValue(undefined);
});

it("useSessionFiles is disabled when sessionId is null", () => {
	renderHook(() => useSessionFiles(null), { wrapper: makeWrapper(makeClient()) });
	expect(get).not.toHaveBeenCalled();
});

it("useSessionFiles queries the session scope url", async () => {
	renderHook(() => useSessionFiles("s1"), { wrapper: makeWrapper(makeClient()) });
	await waitFor(() => {
		expect(get).toHaveBeenCalledWith("/api/uploads?scope=session&session_id=s1");
	});
});

it("useLibraryFiles queries the given scope", async () => {
	renderHook(() => useLibraryFiles("global"), { wrapper: makeWrapper(makeClient()) });
	await waitFor(() => {
		expect(get).toHaveBeenCalledWith("/api/uploads?scope=global");
	});
});

it("useDeleteUpload deletes and invalidates the uploads cache", async () => {
	const client = makeClient();
	const invalidate = vi.spyOn(client, "invalidateQueries");
	const { result } = renderHook(() => useDeleteUpload(), { wrapper: makeWrapper(client) });

	result.current.mutate("f1");

	await waitFor(() => {
		expect(del).toHaveBeenCalledWith("/api/uploads/f1");
	});
	await waitFor(() => {
		expect(invalidate).toHaveBeenCalledWith({ queryKey: ["uploads"] });
	});
});

it("uploadContentUrl builds the content path", () => {
	expect(uploadContentUrl("abc")).toBe("/api/uploads/abc/content");
});

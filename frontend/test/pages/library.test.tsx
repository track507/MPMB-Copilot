import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

// vi.mock is hoisted; the mocks it references must be hoisted too
const { uploadFileSpy, deleteSpy, refetchSpy, authState, filesRef } = vi.hoisted(() => ({
	uploadFileSpy: vi.fn(),
	deleteSpy: vi.fn(),
	refetchSpy: vi.fn(),
	authState: { isAdmin: false },
	filesRef: { current: [] as unknown[] },
}));

vi.mock("@/hooks/use-auth", () => ({ useIsAdmin: () => ({ isAdmin: authState.isAdmin, isLoading: false }) }));
vi.mock("@/lib/http", () => ({ uploadFile: uploadFileSpy }));
vi.mock("@/lib/uploads", () => ({
	useLibraryFiles: () => ({ data: { files: filesRef.current, total: filesRef.current.length }, refetch: refetchSpy }),
	useDeleteUpload: () => ({ mutate: deleteSpy }),
	uploadContentUrl: (id: string) => `/api/uploads/${id}/content`,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import LibraryPage from "@/pages/library";

function fileRow(overrides: Record<string, unknown>): Record<string, unknown> {
	return { id: "f1", filename: "a.js", file_size: 10, uploaded_at: "2026-01-01T00:00:00Z", missing: false, ...overrides };
}

beforeEach(() => {
	uploadFileSpy.mockReset().mockResolvedValue({ id: "new" });
	deleteSpy.mockReset();
	refetchSpy.mockReset().mockResolvedValue(undefined);
	authState.isAdmin = false;
	filesRef.current = [];
});

it("shows the upload control on the user's own library", () => {
	render(<LibraryPage />);
	expect(screen.getByRole("button", { name: /upload files/i })).toBeInTheDocument();
});

it("hides write controls on Shared for non-admins", () => {
	filesRef.current = [fileRow({})];
	render(<LibraryPage />);
	fireEvent.click(screen.getByRole("button", { name: /^shared$/i }));

	expect(screen.queryByRole("button", { name: /upload files/i })).not.toBeInTheDocument();
	expect(screen.getByText(/managed by admins/i)).toBeInTheDocument();
	expect(screen.queryByTitle("Remove")).not.toBeInTheDocument();
});

it("gives admins write controls on Shared", () => {
	authState.isAdmin = true;
	filesRef.current = [fileRow({})];
	render(<LibraryPage />);
	fireEvent.click(screen.getByRole("button", { name: /^shared$/i }));

	expect(screen.getByRole("button", { name: /upload files/i })).toBeInTheDocument();
	expect(screen.getByTitle("Remove")).toBeInTheDocument();
});

it("uploads picked files into the active scope", async () => {
	const { container } = render(<LibraryPage />);
	const input = container.querySelector('input[type="file"]');
	if (input === null) throw new Error("expected a file input");
	const file = new File([new ArrayBuffer(4)], "spells.js");

	fireEvent.change(input, { target: { files: [file] } });

	await waitFor(() => {
		expect(uploadFileSpy).toHaveBeenCalledWith("/api/uploads", file, { scope: "global" });
	});
});

it("flags a file whose bytes are missing", () => {
	filesRef.current = [fileRow({ id: "f2", filename: "gone.js", missing: true })];
	render(<LibraryPage />);
	expect(screen.getByText(/missing on disk/i)).toBeInTheDocument();
});

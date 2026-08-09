import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { ChatWindow } from "@/components/chat/chat-window";
import { useUploadStore } from "@/stores/upload-store";

// vi.mock is hoisted above the module body, so the mocks it references must be hoisted too
const { sendMessage, cancelStream, uploadFile, createSession } = vi.hoisted(() => ({
	sendMessage: vi.fn(),
	cancelStream: vi.fn(),
	uploadFile: vi.fn(),
	createSession: vi.fn(),
}));

vi.mock("react-router", () => ({ useParams: () => ({ sessionId: undefined }) }));
vi.mock("@/hooks/use-sessions", () => ({ useSession: () => ({ data: undefined }) }));
vi.mock("@/hooks/use-chat", () => ({ useChat: () => ({ sendMessage, cancelStream }) }));
vi.mock("@/hooks/use-smooth-text", () => ({ useSmoothText: (text: string) => text }));
vi.mock("@/lib/http", () => ({ apiClient: { post: createSession }, uploadFile }));
vi.mock("@/lib/uploads", () => ({ useSessionFiles: () => ({ data: undefined }), uploadContentUrl: (id: string) => id }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

beforeEach(() => {
	sendMessage.mockClear();
	uploadFile.mockClear();
	createSession.mockClear();
	useUploadStore.getState().clearStaged();
});

it("creates a session, uploads staged files, then sends with their ids", async () => {
	createSession.mockResolvedValue({ id: "sess-1" });
	uploadFile.mockResolvedValue({ id: "file-1" });

	const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
	render(
		<QueryClientProvider client={client}>
			<ChatWindow />
		</QueryClientProvider>
	);

	act(() => {
		useUploadStore.getState().stageFiles([new File([new ArrayBuffer(4)], "a.js")]);
	});

	const textarea = screen.getByPlaceholderText(/MPMB scripting/i);
	fireEvent.change(textarea, { target: { value: "hi" } });
	fireEvent.keyDown(textarea, { key: "Enter" });

	// Wait on the final step so the whole create -> upload -> send flow has settled
	await waitFor(() => {
		expect(sendMessage).toHaveBeenCalled();
	});

	expect(uploadFile).toHaveBeenCalledTimes(1);
	expect(createSession).toHaveBeenCalledWith("/api/sessions", { title: "New Conversation" });
	expect(sendMessage).toHaveBeenCalledWith("hi", expect.objectContaining({ session_id: "sess-1", attached_file_ids: ["file-1"] }));
});

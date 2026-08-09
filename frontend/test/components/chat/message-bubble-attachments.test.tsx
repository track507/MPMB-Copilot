import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { FileOut } from "@/types/uploads";

// Keep the test off the http/query-client import chain that lib/uploads pulls in
vi.mock("@/lib/uploads", () => ({ uploadContentUrl: (id: string) => `/api/uploads/${id}/content` }));

import { MessageBubble } from "@/components/chat/message-bubble";

function attachment(overrides: Partial<FileOut>): FileOut {
	return {
		id: "f1",
		scope: "session",
		session_id: "s1",
		filename: "spells.js",
		original_filename: "spells.js",
		file_size: 10,
		content_type: "text/javascript",
		file_hash: "h",
		uploaded_at: "2026-01-01T00:00:00Z",
		message_id: "m1",
		missing: false,
		...overrides,
	};
}

it("renders an attachment chip linking to the file content", () => {
	render(<MessageBubble role="user" content="here" attachments={[attachment({})]} />);
	const link = screen.getByRole("link", { name: /spells\.js/i });
	expect(link).toHaveAttribute("href", "/api/uploads/f1/content");
	expect(link).toHaveAttribute("download", "spells.js");
});

it("annotates missing and pdf attachments", () => {
	render(
		<MessageBubble
			role="user"
			content="here"
			attachments={[attachment({ id: "f2", filename: "gone.js", missing: true }), attachment({ id: "f3", filename: "guide.pdf" })]}
		/>
	);
	expect(screen.getByText(/missing on disk/i)).toBeInTheDocument();
	expect(screen.getByText(/not yet readable/i)).toBeInTheDocument();
});

it("renders nothing extra when there are no attachments", () => {
	render(<MessageBubble role="user" content="plain" />);
	expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

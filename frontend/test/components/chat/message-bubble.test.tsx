import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("@/lib/uploads", () => ({ uploadContentUrl: (id: string) => `/api/uploads/${id}/content` }));

import { MessageBubble } from "@/components/chat/message-bubble";

it("drops raw html from assistant markdown", () => {
	const { container } = render(<MessageBubble role="assistant" content={'before <img src="x" onerror="alert(1)"> <script>alert(2)</script> after'} />);
	expect(container.querySelector("img")).toBeNull();
	expect(container.querySelector("script")).toBeNull();
	expect(container.querySelector("[onerror]")).toBeNull();
});

it("neutralizes javascript links in assistant markdown", () => {
	render(<MessageBubble role="assistant" content="[run me](javascript:alert(1))" />);
	const link = screen.getByText("run me").closest("a");
	expect(link?.getAttribute("href") ?? "").not.toMatch(/^\s*javascript:/i);
});

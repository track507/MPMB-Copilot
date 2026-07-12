import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MessageActions } from "@/components/chat/message-actions";

const setMutate = vi.fn();
const clearMutate = vi.fn();

vi.mock("@/hooks/use-feedback", () => ({
	useSetFeedback: () => ({ mutate: setMutate }),
	useClearFeedback: () => ({ mutate: clearMutate }),
}));

describe("MessageActions", () => {
	beforeEach(() => {
		setMutate.mockClear();
		clearMutate.mockClear();
	});

	it("copies the message content", async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		Object.assign(navigator, { clipboard: { writeText } });
		render(<MessageActions sessionId="s1" messageId="m1" content="hello world" feedback={null} />);
		fireEvent.click(screen.getByTitle("Copy"));
		// ? copy() awaits the clipboard write before setting the copied state; waitFor flushes that update inside act
		await waitFor(() => {
			expect(writeText).toHaveBeenCalledWith("hello world");
		});
	});

	it("submits a down vote and reveals the note field", () => {
		render(<MessageActions sessionId="s1" messageId="m1" content="x" feedback={null} />);
		fireEvent.click(screen.getByTitle("Bad response"));
		expect(screen.getByPlaceholderText(/what went wrong/i)).toBeInTheDocument();
		expect(setMutate).toHaveBeenCalled();
	});

	it("clears the vote when the active rating is clicked again", () => {
		render(
			<MessageActions
				sessionId="s1"
				messageId="m1"
				content="x"
				feedback={{ rating: "up", note: null, created_at: "", updated_at: "" }}
			/>
		);
		fireEvent.click(screen.getByTitle("Good response"));
		expect(clearMutate).toHaveBeenCalledWith("m1", expect.anything());
	});
});

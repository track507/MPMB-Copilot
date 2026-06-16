import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ModelSelect } from "@/components/settings/model-select";
import type { ModelOption } from "@/types/settings";

const OPTS: ModelOption[] = [
	{ id: "claude-opus-4-8", label: "Claude Opus 4.8", effort: ["low", "high"] },
	{ id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", effort: ["low", "high"] },
];

describe("ModelSelect", () => {
	it("renders a free-form input when there are no options", () => {
		render(<ModelSelect value="llama3" onChange={vi.fn()} options={[]} />);
		expect(screen.getByRole("textbox")).toHaveValue("llama3");
		expect(screen.queryByRole("combobox")).toBeNull();
	});

	it("shows the dropdown with a Custom escape hatch when options exist", () => {
		render(<ModelSelect value="claude-opus-4-8" onChange={vi.fn()} options={OPTS} />);
		expect(screen.getByRole("combobox")).toHaveValue("claude-opus-4-8");
		expect(screen.getByRole("option", { name: "Custom..." })).toBeInTheDocument();
	});

	it("falls back to a custom text input when the value is unknown", () => {
		render(<ModelSelect value="mystery-model" onChange={vi.fn()} options={OPTS} />);
		expect(screen.getByRole("textbox")).toHaveValue("mystery-model");
	});

	it("calls onChange with the chosen model id", async () => {
		const onChange = vi.fn();
		render(<ModelSelect value="claude-opus-4-8" onChange={onChange} options={OPTS} />);
		await userEvent.selectOptions(screen.getByRole("combobox"), "claude-sonnet-4-6");
		expect(onChange).toHaveBeenCalledWith("claude-sonnet-4-6");
	});
});

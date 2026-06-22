import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RerankSelect } from "@/components/settings/rerank-select";
import type { RerankModelOption } from "@/types/settings";

const OPTS: RerankModelOption[] = [
	{ provider: "fastembed", id: "Xenova/ms-marco-MiniLM-L-6-v2", label: "MiniLM L6", pinned: true, status: "ready" },
	{ provider: "fastembed", id: "BAAI/bge-reranker-base", label: "bge-reranker-base", pinned: false, status: "ready" },
	{ provider: "cohere", id: "rerank-english-v3.0", label: "Cohere v3", pinned: false, status: "installable" },
];

describe("RerankSelect", () => {
	it("renders the current selection", () => {
		render(<RerankSelect value="Xenova/ms-marco-MiniLM-L-6-v2" options={OPTS} onChange={vi.fn()} />);
		expect(screen.getByRole("combobox")).toHaveValue("Xenova/ms-marco-MiniLM-L-6-v2");
	});

	it("disables non-ready entries", () => {
		render(<RerankSelect value="Xenova/ms-marco-MiniLM-L-6-v2" options={OPTS} onChange={vi.fn()} />);
		expect(screen.getByRole("option", { name: /Cohere v3/ })).toBeDisabled();
	});

	it("calls onChange with provider and id", async () => {
		const onChange = vi.fn();
		render(<RerankSelect value="Xenova/ms-marco-MiniLM-L-6-v2" options={OPTS} onChange={onChange} />);
		await userEvent.selectOptions(screen.getByRole("combobox"), "BAAI/bge-reranker-base");
		expect(onChange).toHaveBeenCalledWith("fastembed", "BAAI/bge-reranker-base");
	});
});

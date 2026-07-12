import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { AdminRoute } from "@/components/auth/admin-route";

const mocks = vi.hoisted(() => ({ useIsAdmin: vi.fn() }));

vi.mock("@/hooks/use-auth", () => ({ useIsAdmin: mocks.useIsAdmin }));

describe("AdminRoute", () => {
	it("renders children for admins", () => {
		mocks.useIsAdmin.mockReturnValue({ isAdmin: true, isLoading: false });
		render(
			<MemoryRouter>
				<AdminRoute>
					<p>secret settings</p>
				</AdminRoute>
			</MemoryRouter>
		);
		expect(screen.getByText("secret settings")).toBeInTheDocument();
	});

	it("renders the not-found page for non-admins (no discoverability)", async () => {
		mocks.useIsAdmin.mockReturnValue({ isAdmin: false, isLoading: false });
		render(
			<MemoryRouter>
				<AdminRoute>
					<p>secret settings</p>
				</AdminRoute>
			</MemoryRouter>
		);
		expect(screen.queryByText("secret settings")).not.toBeInTheDocument();
		// ? The exact same 404 page an unknown route gets - no "admin required" tell
		expect(await screen.findByText("Page not found")).toBeInTheDocument();
	});
});

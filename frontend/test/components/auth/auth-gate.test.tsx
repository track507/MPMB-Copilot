import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { AuthGate } from "@/components/auth/auth-gate";
import type { AuthState } from "@/types/auth";

const mockState = vi.hoisted(() => ({ current: undefined as AuthState | undefined, loading: false }));
vi.mock("@/hooks/use-auth", () => ({
	useAuthState: () => ({ data: mockState.current, isLoading: mockState.loading, isError: false }),
}));

function renderGate(): void {
	render(
		<MemoryRouter initialEntries={["/"]}>
			<Routes>
				<Route path="/login" element={<div>login page</div>} />
				<Route path="/setup" element={<div>setup page</div>} />
				<Route
					path="/"
					element={
						<AuthGate>
							<div>the app</div>
						</AuthGate>
					}
				/>
			</Routes>
		</MemoryRouter>
	);
}

describe("AuthGate", () => {
	it("redirects to setup when setup is required", () => {
		mockState.current = { state: "setup_required" };
		renderGate();
		expect(screen.getByText("setup page")).toBeInTheDocument();
	});

	it("redirects to login when login is required", () => {
		mockState.current = { state: "login_required" };
		renderGate();
		expect(screen.getByText("login page")).toBeInTheDocument();
	});

	it("renders children when authenticated", () => {
		mockState.current = { state: "authenticated", user: { username: "t", role: "admin" } };
		renderGate();
		expect(screen.getByText("the app")).toBeInTheDocument();
	});
});

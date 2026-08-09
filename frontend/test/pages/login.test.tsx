import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/pages/login";

const mutate = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-auth", () => ({
	useAuthState: () => ({ data: { state: "login_required" } }),
	useLogin: () => ({ mutate, isPending: false }),
}));
vi.mock("@tanstack/react-router", () => ({
	useNavigate: () => () => undefined,
}));

describe("LoginPage", () => {
	it("submits credentials", async () => {
		render(<LoginPage />);
		await userEvent.type(screen.getByLabelText("Username"), "terrence");
		await userEvent.type(screen.getByLabelText("Password"), "hunter2hunter2");
		await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
		expect(mutate).toHaveBeenCalledWith({ username: "terrence", password: "hunter2hunter2" }, expect.anything());
	});

	it("shows validation errors on empty submit", async () => {
		render(<LoginPage />);
		await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
		expect(await screen.findByText("Username is required")).toBeInTheDocument();
	});
});

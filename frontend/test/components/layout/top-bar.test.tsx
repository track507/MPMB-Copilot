import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

// vi.mock is hoisted; the state it references must be hoisted too
const { state } = vi.hoisted(() => {
	const state: {
		matches: Array<{ staticData: Record<string, unknown> }>;
		params: { sessionId?: string };
		session: { title: string } | undefined;
		index: Record<string, unknown> | undefined;
	} = { matches: [], params: {}, session: undefined, index: { status: "ready", total_vectors: 11329 } };
	return { state };
});

vi.mock("@tanstack/react-router", () => ({
	useMatches: () => state.matches,
	useParams: () => state.params,
	useNavigate: () => vi.fn(),
}));
vi.mock("@/hooks/use-settings", () => ({ useIndexStatus: () => ({ data: state.index }) }));
vi.mock("@/hooks/use-sessions", () => ({ useSession: () => ({ data: state.session }) }));
vi.mock("@/hooks/use-auth", () => ({ useLogout: () => ({ mutate: vi.fn() }) }));

import { TopBar } from "@/components/layout/top-bar";

beforeEach(() => {
	state.matches = [];
	state.params = {};
	state.session = undefined;
	state.index = { status: "ready", total_vectors: 11329 };
});

it("shows the index status on a chat route, titled from the live session", () => {
	state.matches = [{ staticData: { chat: true } }];
	state.params = { sessionId: "s1" };
	state.session = { title: "Adding a subclass" };

	render(<TopBar />);

	expect(screen.getByText("Adding a subclass")).toBeInTheDocument();
	expect(screen.getByText(/index ready \(11329 vectors\)/i)).toBeInTheDocument();
});

it("falls back to New chat when a chat route has no session yet", () => {
	state.matches = [{ staticData: { title: "New chat", chat: true } }];

	render(<TopBar />);

	expect(screen.getByText("New chat")).toBeInTheDocument();
});

it("shows a page title and description instead of the index status off chat routes", () => {
	state.matches = [{ staticData: { title: "Library", description: "Files the assistant can read across your chats." } }];

	render(<TopBar />);

	expect(screen.getByText("Library")).toBeInTheDocument();
	expect(screen.getByText("Files the assistant can read across your chats.")).toBeInTheDocument();
	expect(screen.queryByText(/index ready/i)).not.toBeInTheDocument();
});

it("takes the deepest titled match so a nested route wins", () => {
	state.matches = [{ staticData: {} }, { staticData: { title: "Admin", description: "Instance configuration and operations." } }];

	render(<TopBar />);

	expect(screen.getByText("Admin")).toBeInTheDocument();
});

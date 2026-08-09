/* eslint-disable react-refresh/only-export-components -- router entry module, not a fast-refresh component file */
import { createRootRouteWithContext, createRoute, createRouter, Outlet } from "@tanstack/react-router";
import { lazy } from "react";
import { requireAdmin, requireAuth } from "./routes/guards";
import { queryClient } from "@/lib/query-client";
import RootLayout from "./components/layout/root-layout";
import { AdminLayout } from "@/components/layout/admin-layout";
import type { QueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";

interface RouterContext {
	queryClient: QueryClient;
}

// * Lazy page modules
const HomePage = lazy(async () => import("@/pages/home"));
const LoginPage = lazy(async () => import("@/pages/login"));
const SetupPage = lazy(async () => import("@/pages/setup"));
const NotFoundPage = lazy(async () => import("@/pages/not-found"));
const LibraryPage = lazy(async () => import("@/pages/library"));
const AccountPage = lazy(async () => import("@/pages/account"));
const SettingsPage = lazy(async () => import("@/pages/settings"));

function PageLoader(): ReactElement {
	return (
		<div className="flex h-full items-center justify-center">
			<div className="size-6 animate-spin rounded-full border-2 border-solid border-primary border-r-transparent" />
		</div>
	);
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
	component: () => <Outlet />,
	notFoundComponent: NotFoundPage,
});

const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: "/login", component: LoginPage });
const setupRoute = createRoute({ getParentRoute: () => rootRoute, path: "/setup", component: SetupPage });

// * Pathless auth layout: id (not path); its beforeLoad gates every child
const authLayoutRoute = createRoute({
	getParentRoute: () => rootRoute,
	id: "auth",
	beforeLoad: async ({ context }) => requireAuth(context.queryClient),
	component: RootLayout, // sidebar + top-bar + <Outlet/>
});

const indexRoute = createRoute({ getParentRoute: () => authLayoutRoute, path: "/", component: HomePage, staticData: { title: "New chat", chat: true } });
const chatRoute = createRoute({ getParentRoute: () => authLayoutRoute, path: "chat/$sessionId", component: HomePage, staticData: { chat: true } });
const libraryRoute = createRoute({ getParentRoute: () => authLayoutRoute, path: "library", component: LibraryPage, staticData: { title: "Library" } });
const accountRoute = createRoute({ getParentRoute: () => authLayoutRoute, path: "account", component: AccountPage, staticData: { title: "Account" } });

// * Admin console: its own layout shell + admin guard; hosts the existing panel intact
const adminLayoutRoute = createRoute({
	getParentRoute: () => authLayoutRoute,
	path: "admin",
	beforeLoad: async ({ context }) => requireAdmin(context.queryClient),
	component: AdminLayout,
	staticData: {
		title: "Admin",
	},
});
const adminSettingsRoute = createRoute({ getParentRoute: () => adminLayoutRoute, path: "/", component: SettingsPage });

const routeTree = rootRoute.addChildren([
	loginRoute,
	setupRoute,
	authLayoutRoute.addChildren([indexRoute, chatRoute, libraryRoute, accountRoute, adminLayoutRoute.addChildren([adminSettingsRoute])]),
]);

export const router = createRouter({
	routeTree,
	context: { queryClient },
	defaultPendingComponent: PageLoader,
	defaultPendingMs: 150,
	defaultPendingMinMs: 300,
	defaultPreload: "intent",
});

// * Register for app-wide type safety on Link/useNavigate/useParams
declare module "@tanstack/react-router" {
	interface Register {
		router: typeof router;
	}
	interface StaticDataRouteOption {
		readonly title?: string;
		readonly chat?: boolean;
	}
}

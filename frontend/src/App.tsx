import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import RootLayout from "./components/layout/root-layout";
import type { ReactElement } from "react";
import { ApiError } from "@/lib/http";
import { AuthGate } from "@/components/auth/auth-gate";
import { AdminRoute } from "@/components/auth/admin-route";

const HomePage = lazy(async () => import("./pages/home"));
const SettingsPage = lazy(async () => import("./pages/settings"));
const NotFoundPage = lazy(async () => import("./pages/not-found"));
const LoginPage = lazy(async () => import("./pages/login"));
const SetupPage = lazy(async () => import("./pages/setup"));
const LibraryPage = lazy(async () => import("./pages/library"));

const queryClient = new QueryClient({
	queryCache: new QueryCache({
		onError: (error) => {
			// ! Session died mid-use: refetch auth state so the AuthGate bounces to /login
			if (error instanceof ApiError && error.status === 401) {
				void queryClient.invalidateQueries({ queryKey: ["auth-state"] });
			}
		},
	}),
	defaultOptions: {
		queries: {
			staleTime: 5 * 60 * 1000,
			retry: 1,
			refetchOnWindowFocus: true,
		},
	},
});

function PageLoader(): ReactElement {
	return (
		<div className="flex h-full items-center justify-center">
			<div className="h-6 w-6 animate-spin rounded-full border-2 border-solid border-primary border-r-transparent" />
		</div>
	);
}

export default function App(): ReactElement {
	return (
		<QueryClientProvider client={queryClient}>
			<BrowserRouter>
				<Routes>
					<Route
						path="login"
						element={
							<Suspense fallback={<PageLoader />}>
								<LoginPage />
							</Suspense>
						}
					/>
					<Route
						path="setup"
						element={
							<Suspense fallback={<PageLoader />}>
								<SetupPage />
							</Suspense>
						}
					/>
					<Route
						element={
							<AuthGate>
								<RootLayout />
							</AuthGate>
						}>
						<Route
							index
							element={
								<Suspense fallback={<PageLoader />}>
									<HomePage />
								</Suspense>
							}
						/>
						<Route
							path="chat/:sessionId"
							element={
								<Suspense fallback={<PageLoader />}>
									<HomePage />
								</Suspense>
							}
						/>
						<Route
							path="library"
							element={
								<Suspense fallback={<PageLoader />}>
									<LibraryPage />
								</Suspense>
							}
						/>
						<Route
							path="settings"
							element={
								<AdminRoute>
									<Suspense fallback={<PageLoader />}>
										<SettingsPage />
									</Suspense>
								</AdminRoute>
							}
						/>
						<Route
							path="*"
							element={
								<Suspense fallback={<PageLoader />}>
									<NotFoundPage />
								</Suspense>
							}
						/>
					</Route>
				</Routes>
			</BrowserRouter>
			<ReactQueryDevtools initialIsOpen={false} />
		</QueryClientProvider>
	);
}

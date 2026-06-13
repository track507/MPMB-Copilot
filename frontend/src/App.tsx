import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import RootLayout from "./components/layout/root-layout";
import type { ReactElement } from "react";

const HomePage = lazy(async () => import("./pages/home"));
const SettingsPage = lazy(async () => import("./pages/settings"));
const NotFoundPage = lazy(async () => import("./pages/not-found"));

const queryClient = new QueryClient({
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
					<Route element={<RootLayout />}>
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
							path="settings"
							element={
								<Suspense fallback={<PageLoader />}>
									<SettingsPage />
								</Suspense>
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

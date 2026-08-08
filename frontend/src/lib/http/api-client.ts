/**
 * Typed JSON fetch verbs over the shared http core
 *
 * Usage:
 * ```ts
 * const { data } = useQuery({
 *     queryKey: ["sessions"],
 *     queryFn: () => apiClient.get<Session[]>("/api/sessions"),
 * });
 * ```
 */

import { request } from "./core";

export const apiClient = {
	get: async <T>(path: string): Promise<T> => request<T>(path),

	post: async <T>(path: string, body: unknown): Promise<T> => request<T>(path, { method: "POST", body: JSON.stringify(body) }),

	put: async <T>(path: string, body: unknown): Promise<T> => request<T>(path, { method: "PUT", body: JSON.stringify(body) }),

	patch: async <T>(path: string, body: unknown): Promise<T> => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),

	delete: async <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" }),
} as const;

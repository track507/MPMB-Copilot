/**
 * Typed fetch wrapper for backend API calls.
 *
 * Designed to be used as the queryFn in TanStack Query hooks.
 *
 * Usage:
 * ```ts
 * const { data } = useQuery({
 *     queryKey: ["sessions"],
 *     queryFn: () => apiClient.get<Session[]>("/api/sessions"),
 * });
 * ```
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface ProblemDetail {
	readonly type: string;
	readonly title: string;
	readonly status: number;
	readonly detail: string;
	readonly instance?: string;
}

export class ApiError extends Error {
	readonly status: number;
	readonly problem: ProblemDetail | null;

	constructor(status: number, problem: ProblemDetail | null) {
		super(problem?.detail ?? `Request failed with status ${String(status)}`);
		this.name = "ApiError";
		this.status = status;
		this.problem = problem;
	}
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const url = `${BASE_URL}${path}`;

	const headers = new Headers(options?.headers);
	headers.set("Content-Type", "application/json");

	const response = await fetch(url, {
		...options,
		headers,
	});

	if (!response.ok) {
		let problem: ProblemDetail | null = null;
		try {
			problem = (await response.json()) as ProblemDetail;
		} catch {
			// Response body wasn't valid JSON - problem stays null
		}
		throw new ApiError(response.status, problem);
	}

	// Handle 204 No Content
	if (response.status === 204) {
		return undefined as T;
	}

	return (await response.json()) as T;
}

export const apiClient = {
	get: async <T>(path: string): Promise<T> => request<T>(path),

	post: async <T>(path: string, body: unknown): Promise<T> =>
		request<T>(path, {
			method: "POST",
			body: JSON.stringify(body),
		}),

	put: async <T>(path: string, body: unknown): Promise<T> =>
		request<T>(path, {
			method: "PUT",
			body: JSON.stringify(body),
		}),

	patch: async <T>(path: string, body: unknown): Promise<T> =>
		request<T>(path, {
			method: "PATCH",
			body: JSON.stringify(body),
		}),

	delete: async <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" }),
} as const;

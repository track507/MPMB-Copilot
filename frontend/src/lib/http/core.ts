/**
 * Shared HTTP core: base URL, the RFC 9457 problem shape, ApiError, and the single body -> ApiError adapter
 *
 * Every transport (fetch verbs, XHR upload, SSE stream) builds on this so there is one base URL and one error contract across the app
 */

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export interface ProblemDetail {
	readonly type: string;
	readonly title: string;
	readonly status: number;
	readonly detail: string;
	readonly instance?: string;
	readonly errors?: ReadonlyArray<{ readonly field: string; readonly message: string }>;
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

function isProblem(body: unknown): body is ProblemDetail {
	return typeof body === "object" && body !== null && "type" in body && "detail" in body;
}

/** The single place a response body becomes an ApiError */
export function toApiError(status: number, body: unknown): ApiError {
	return new ApiError(status, isProblem(body) ? body : null);
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
	const headers = new Headers(options?.headers);
	// FormData sets its own multipart boundary; only force JSON otherwise.
	if (!(options?.body instanceof FormData)) headers.set("Content-Type", "application/json");

	const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

	if (!response.ok) {
		let body: unknown = null;
		try {
			body = await response.json();
			// eslint-disable-next-line no-empty
		} catch {}
		throw toApiError(response.status, body);
	}

	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

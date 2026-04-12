/** Mirrors backend ChatRequest / ChatResponse / ChatStreamChunk schemas. */

export interface ChatRequest {
	readonly message: string;
	readonly session_id?: string | undefined;
	readonly provider?: string | undefined;
	readonly model?: string | undefined;
	readonly temperature?: number | undefined;
	readonly max_tokens?: number | undefined;
	readonly include_source?: boolean | undefined;
	readonly edition?: string | undefined;
}

export interface ChatResponse {
	readonly response: string;
	readonly conversation_id: string;
	readonly sources: SourceReference[] | null;
	readonly metadata: ChatMetadata;
}

export interface ChatStreamChunk {
	readonly chunk: string;
	readonly done: boolean;
	readonly metadata?: ChatMetadata | undefined;
}

export interface ChatMetadata {
	readonly provider?: string | undefined;
	readonly model?: string | undefined;
	readonly prompt_tokens?: number | undefined;
	readonly completion_tokens?: number | undefined;
	readonly total_tokens?: number | undefined;
	readonly latency_ms?: number | undefined;
	readonly retrieval_time_ms?: number | undefined;
	readonly chunks_retrieved?: number | undefined;
}

export interface SourceReference {
	readonly file: string;
	readonly content: string;
	readonly score: number;
	readonly line_range?: [number, number] | undefined;
}

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

export interface ChatUsage {
	readonly input_tokens?: number | undefined;
	readonly output_tokens?: number | undefined;
	readonly total_tokens?: number | undefined;
	readonly cache_read_tokens?: number | undefined;
	readonly cache_creation_tokens?: number | undefined;
}

export interface ChatTiming {
	readonly total_ms?: number | undefined;
	readonly retrieval_ms?: number | undefined;
	readonly generation_ms?: number | undefined;
}

export interface ChatRetrieval {
	readonly total_chunks?: number | undefined;
	readonly intent?: string | undefined;
	readonly edition?: string | undefined;
	readonly object_type?: string | undefined;
	readonly authoritative_count?: number | undefined;
	readonly examples_count?: number | undefined;
}

export interface ChatMetadata {
	readonly conversation_id?: string | undefined;
	readonly provider?: string | undefined;
	readonly model?: string | undefined;
	readonly usage?: ChatUsage | undefined;
	readonly timing?: ChatTiming | undefined;
	readonly retrieval?: ChatRetrieval | undefined;
}

export interface SourceReference {
	readonly file: string;
	readonly content: string;
	readonly score: number;
	readonly line_range?: [number, number] | undefined;
}

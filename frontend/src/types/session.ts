/** Mirrors backend SessionOut / SessionDetailOut / MessageOut schemas. */
import type { ChatToolsMetadata } from "@/types/chat";

export interface MessageMetadata {
	readonly retrieval?: Record<string, unknown> | null;
	readonly timing?: Record<string, unknown>;
	readonly tools?: ChatToolsMetadata;
	readonly [key: string]: unknown;
}

export interface Session {
	readonly id: string;
	readonly title: string;
	readonly created_at: string;
	readonly updated_at: string;
	readonly user_id: string | null;
	readonly settings: Record<string, unknown>;
	readonly meta_data: Record<string, unknown>;
	readonly message_count: number;
}

export interface SessionDetail extends Session {
	readonly messages: Message[];
}

export interface SessionListResponse {
	readonly sessions: Session[];
	readonly total: number;
	readonly limit: number;
	readonly offset: number;
}

export interface SessionCreate {
	readonly title?: string | undefined;
	readonly edition?: string | undefined;
	readonly settings?: Record<string, unknown> | undefined;
}

export interface SessionUpdate {
	readonly title?: string | undefined;
	readonly settings?: Record<string, unknown> | undefined;
	readonly meta_data?: Record<string, unknown> | undefined;
}

export interface Message {
	readonly id: string;
	readonly session_id: string;
	readonly role: "user" | "assistant" | "system";
	readonly content: MessageContent;
	readonly created_at: string;
	readonly sequence_number: number;
	readonly provider: string | null;
	readonly model: string | null;
	readonly prompt_tokens: number;
	readonly completion_tokens: number;
	readonly total_tokens: number;
	readonly latency_ms: number | null;
	readonly stop_reason: string | null;
	readonly meta_data: MessageMetadata;
}

export interface MessageContent {
	readonly text: string;
	readonly sources?: SourceReference[] | undefined;
}

export interface SourceReference {
	readonly file: string;
	readonly content: string;
	readonly score: number;
	readonly line_range?: [number, number] | undefined;
}

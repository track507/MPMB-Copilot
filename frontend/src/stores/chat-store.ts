import { create } from "zustand";
import type { ChatMetadata, ToolEventPayload } from "@/types/chat";

export interface DisplayMessage {
	readonly id: string;
	readonly role: "user" | "assistant" | "system";
	readonly text: string;
}

interface ChatStoreState {
	pendingUserMessage: DisplayMessage | null;
	streamedText: string;
	isStreaming: boolean;
	metadata: ChatMetadata | null;
	activeToolCount: number;
	activeTool: string | null;
	sawToolThisStream: boolean;
}

interface ChatStoreActions {
	addUserMessage: (text: string) => void;
	appendStreamChunk: (chunk: string) => void;
	onToolStart: (tool: ToolEventPayload) => void;
	onToolEnd: (tool: ToolEventPayload) => void;
	completeStream: (metadata: ChatMetadata | null) => void;
	clearOptimistic: () => void;
	reset: () => void;
}

type ChatStore = ChatStoreState & ChatStoreActions;

const initialState: ChatStoreState = {
	pendingUserMessage: null,
	streamedText: "",
	isStreaming: false,
	metadata: null,
	activeToolCount: 0,
	activeTool: null,
	sawToolThisStream: false,
};

export const useChatStore = create<ChatStore>((set) => ({
	...initialState,

	addUserMessage: (text: string) => {
		set({
			pendingUserMessage: {
				id: `pending-${String(Temporal.Now.instant().epochMilliseconds)}`,
				role: "user",
				text,
			},
			isStreaming: true,
			streamedText: "",
			metadata: null,
			activeToolCount: 0,
			activeTool: null,
			sawToolThisStream: false,
		});
	},

	appendStreamChunk: (chunk: string) => {
		set((state) => ({ streamedText: state.streamedText + chunk }));
	},

	onToolStart: (tool: ToolEventPayload) => {
		set((state) => ({
			activeToolCount: state.activeToolCount + 1,
			activeTool: tool.name,
			sawToolThisStream: true,
		}));
	},

	onToolEnd: () => {
		set((state) => {
			const activeToolCount = Math.max(0, state.activeToolCount - 1);
			// ? Clear the label only once no tool is in flight; tools run mostly sequentially
			return { activeToolCount, activeTool: activeToolCount === 0 ? null : state.activeTool };
		});
	},

	completeStream: (metadata: ChatMetadata | null) => {
		set({ isStreaming: false, metadata, activeToolCount: 0, activeTool: null });
	},

	clearOptimistic: () => {
		set({ pendingUserMessage: null, streamedText: "", activeToolCount: 0, activeTool: null, sawToolThisStream: false });
	},

	reset: () => {
		set(initialState);
	},
}));

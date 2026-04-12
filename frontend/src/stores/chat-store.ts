import { create } from "zustand";
import type { ChatMetadata } from "@/types/chat";

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
}

interface ChatStoreActions {
	addUserMessage: (text: string) => void;
	appendStreamChunk: (chunk: string) => void;
	completeStream: (metadata: ChatMetadata | null) => void;
	reset: () => void;
}

type ChatStore = ChatStoreState & ChatStoreActions;

const initialState: ChatStoreState = {
	pendingUserMessage: null,
	streamedText: "",
	isStreaming: false,
	metadata: null,
};

export const useChatStore = create<ChatStore>((set) => ({
	...initialState,

	addUserMessage: (text: string) => {
		set({
			pendingUserMessage: {
				id: `pending-${String(Date.now())}`,
				role: "user",
				text,
			},
			isStreaming: true,
			streamedText: "",
			metadata: null,
		});
	},

	appendStreamChunk: (chunk: string) => {
		set((state) => ({
			streamedText: state.streamedText + chunk,
		}));
	},

	completeStream: (metadata: ChatMetadata | null) => {
		set({
			isStreaming: false,
			metadata,
		});
	},

	reset: () => {
		set(initialState);
	},
}));

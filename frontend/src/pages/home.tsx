import { useParams } from "@tanstack/react-router";
import { ChatWindow } from "@/components/chat/chat-window";
import type { ReactElement } from "react";

export default function HomePage(): ReactElement {
	const { sessionId } = useParams({ strict: false });
	return <ChatWindow key={sessionId ?? "new"} />;
}

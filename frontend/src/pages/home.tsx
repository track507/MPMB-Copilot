import { useParams } from "react-router";
import { ChatWindow } from "@/components/chat/chat-window";
import type { ReactElement } from "react";

export default function HomePage(): ReactElement {
	const { sessionId } = useParams();

	return <ChatWindow key={sessionId ?? "new"} />;
}

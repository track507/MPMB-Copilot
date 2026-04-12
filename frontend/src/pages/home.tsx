import { useSearchParams } from "react-router";
import { ChatWindow } from "@/components/chat/chat-window";
import type { ReactElement } from "react";

export default function HomePage(): ReactElement {
	const [searchParams] = useSearchParams();
	const sessionId = searchParams.get("session");

	return <ChatWindow key={sessionId ?? "new"} />;
}

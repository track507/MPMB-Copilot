import { Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./code-block";
import { SourceCitation } from "./source-citation";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";
import type { ComponentPropsWithoutRef } from "react";
import type { SourceReference } from "@/types/chat";

interface MessageBubbleProps {
	readonly role: "user" | "assistant" | "system";
	readonly content: string;
	readonly sources?: SourceReference[] | undefined;
	readonly isStreaming?: boolean | undefined;
}

type CodeProps = ComponentPropsWithoutRef<"code">;

export function MessageBubble({ role, content, sources, isStreaming = false }: MessageBubbleProps): ReactElement {
	const isUser = role === "user";

	return (
		<div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
			<div
				className={cn(
					"flex size-8 shrink-0 items-center justify-center rounded-full",
					isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
				)}>
				{isUser ? <User className="size-4" /> : <Bot className="size-4" />}
			</div>

			<div className={cn("max-w-[85%] space-y-2", isUser && "text-right")}>
				<div
					className={cn(
						"inline-block rounded-lg px-4 py-2.5 text-sm leading-relaxed",
						isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
					)}>
					{isUser ? (
						<div className="whitespace-pre-wrap text-left">{content}</div>
					) : (
						<div
							className={cn(
								"prose prose-sm dark:prose-invert max-w-none",
								"prose-pre:m-0 prose-pre:bg-transparent prose-pre:p-0",
								"prose-code:before:content-none prose-code:after:content-none"
							)}>
							<ReactMarkdown
								remarkPlugins={[remarkGfm]}
								components={{
									code: ({ className, children, ...props }: CodeProps) => {
										const langMatch = /language-(\w+)/.exec(className ?? "");
										if (langMatch === null) {
											return (
												<code className="rounded bg-background/60 px-1 py-0.5 font-mono text-xs" {...props}>
													{children}
												</code>
											);
										}
										const code = (
											typeof children === "string"
												? children
												: Array.isArray(children)
													? children.filter((c): c is string => typeof c === "string").join("")
													: ""
										).replace(/\n$/, "");
										return <CodeBlock code={code} language={langMatch[1] ?? "text"} />;
									},
									pre: ({ children }) => <>{children}</>,
									table: ({ children, ...props }) => (
										<div className="my-2 overflow-x-auto">
											<table className="w-full border-collapse text-xs" {...props}>
												{children}
											</table>
										</div>
									),
									th: ({ children, ...props }) => (
										<th className="border border-border bg-muted/50 px-2 py-1 text-left font-medium" {...props}>
											{children}
										</th>
									),
									td: ({ children, ...props }) => (
										<td className="border border-border px-2 py-1 align-top" {...props}>
											{children}
										</td>
									),
								}}>
								{content}
							</ReactMarkdown>
						</div>
					)}
					{isStreaming && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-current" />}
				</div>

				{sources !== undefined && sources.length > 0 && <SourceCitation sources={sources} />}
			</div>
		</div>
	);
}

import { Bot, TriangleAlert, User, Zap } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "./code-block";
import { SourceCitation } from "./source-citation";
import { cn } from "@/lib/utils";
import type { ReactElement } from "react";
import type { ComponentPropsWithoutRef } from "react";
import type { ChatToolsMetadata, SourceReference } from "@/types/chat";

interface MessageBubbleProps {
	readonly role: "user" | "assistant" | "system";
	readonly content: string;
	readonly sources?: SourceReference[] | undefined;
	readonly isStreaming?: boolean | undefined;
	readonly tools?: ChatToolsMetadata | undefined;
	readonly cacheReadTokens?: number | undefined;
	readonly stopReason?: string | undefined;
}

type CodeProps = ComponentPropsWithoutRef<"code">;

export function MessageBubble({ role, content, sources, isStreaming = false, tools, cacheReadTokens, stopReason }: MessageBubbleProps): ReactElement {
	const isUser = role === "user";

	return (
		<div className={cn("flex min-w-0 gap-3", isUser && "flex-row-reverse")}>
			<div
				className={cn(
					"flex size-8 shrink-0 items-center justify-center rounded-full",
					isUser ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"
				)}>
				{isUser ? <User className="size-4" /> : <Bot className="size-4" />}
			</div>

			<div className={cn("min-w-0 max-w-[85%] space-y-2", isUser && "text-right")}>
				<div
					className={cn(
						"inline-block max-w-full overflow-hidden rounded-lg px-4 py-2.5 text-sm leading-relaxed",
						isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
					)}>
					{isUser ? (
						<div className="whitespace-pre-wrap text-left">{content}</div>
					) : (
						<div
							className={cn(
								"prose prose-sm dark:prose-invert min-w-0 max-w-none",
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
										<div className="my-2 max-w-full overflow-x-auto">
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

				{!isUser && stopReason === "length" && (
					<div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-500">
						<TriangleAlert className="size-3.5 shrink-0" />
						<span>Response cut off at the token limit. Raise Max Tokens in settings, or ask it to continue.</span>
					</div>
				)}

				{!isUser && cacheReadTokens !== undefined && cacheReadTokens > 0 && (
					<div
						className="inline-flex items-center gap-1 rounded-full bg-muted/60 px-2 py-0.5 text-[10px] text-muted-foreground"
						title={`${cacheReadTokens.toLocaleString()} input tokens read from cache`}>
						<Zap className="size-3" />
						cached
					</div>
				)}

				{!isUser && tools !== undefined && tools.total_calls > 0 && (
					<details className="mt-2 text-xs text-muted-foreground">
						<summary className="cursor-pointer">
							Used {tools.total_calls} tool{tools.total_calls === 1 ? "" : "s"}
						</summary>
						<ul className="mt-1 list-disc pl-5 text-left">
							{tools.calls.map((call, i) => (
								<li key={i}>
									{call.name} - {call.status} ({call.duration_ms.toFixed(0)}ms)
								</li>
							))}
						</ul>
					</details>
				)}
			</div>
		</div>
	);
}

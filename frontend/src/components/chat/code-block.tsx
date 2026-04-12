import { Check, Copy } from "lucide-react";
import { useCallback, useState } from "react";
import type { ReactElement } from "react";

interface CodeBlockProps {
	readonly code: string;
	readonly language?: string;
}

export function CodeBlock({ code, language = "javascript" }: CodeBlockProps): ReactElement {
	const [copied, setCopied] = useState(false);

	const handleCopy = useCallback(async () => {
		await navigator.clipboard.writeText(code);
		setCopied(true);
		setTimeout(() => {
			setCopied(false);
		}, 2000);
	}, [code]);

	return (
		<div className="not-prose my-2 overflow-hidden rounded-md border border-zinc-700 bg-zinc-900 text-zinc-100">
			<div className="flex items-center justify-between border-b border-zinc-700 bg-zinc-800 px-3 py-1.5">
				<span className="text-xs text-zinc-400">{language}</span>
				<button
					type="button"
					onClick={() => {
						void handleCopy();
					}}
					className="flex items-center gap-1 text-xs text-zinc-400 transition-colors hover:text-zinc-100">
					{copied ? (
						<>
							<Check className="size-3" />
							Copied
						</>
					) : (
						<>
							<Copy className="size-3" />
							Copy
						</>
					)}
				</button>
			</div>

			<pre className="overflow-x-auto p-3 text-xs leading-relaxed">
				<code className="font-mono text-zinc-100">{code}</code>
			</pre>
		</div>
	);
}

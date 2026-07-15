import { lint } from "./lint.mjs";

async function readStdin() {
	/** @type {Buffer[]} */
	const chunks = [];
	for await (const chunk of process.stdin) chunks.push(chunk);
	return Buffer.concat(chunks).toString("utf8");
}

try {
	const input = JSON.parse(await readStdin());
	if (typeof input.source !== "string") throw new Error("missing string field: source");
	const { findings, notes } = lint(input.source, input.edition);
	const counts = {
		error: findings.filter((f) => f.severity === "error").length,
		warning: findings.filter((f) => f.severity === "warning").length,
	};
	process.stdout.write(JSON.stringify({ findings, counts, notes }) + "\n");
} catch (err) {
	process.stderr.write(String(err instanceof Error ? err.message : err) + "\n");
	process.exitCode = 1;
}

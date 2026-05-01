#!/usr/bin/env node
// Pre-flight port check. Fail fast with a clear message if the port is already
// bound, so a stale uvicorn/dev server can't silently coexist with a new one.
import net from "node:net";

const port = Number(process.argv[2] ?? 8000);
const label = process.argv[3] ?? `port ${port}`;

const server = net.createServer();
server.unref();

server.once("error", (err) => {
	if (err.code === "EADDRINUSE") {
		console.error(`\n[check-port] ${label} is already in use.`);
		console.error(
			`[check-port] Likely a stale process from a previous run. To fix:\n` +
				`  Windows: Get-Process python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force\n` +
				`  macOS/Linux: lsof -ti:${port} | xargs -r kill -9\n`
		);
		process.exit(1);
	}
	console.error(`[check-port] unexpected error checking ${label}:`, err);
	process.exit(1);
});

server.once("listening", () => {
	server.close(() => process.exit(0));
});

server.listen(port, "127.0.0.1");

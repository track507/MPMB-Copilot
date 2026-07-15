import { execFile } from "node:child_process";
import path from "node:path";
import { describe, expect, it } from "vitest";

const CLI = path.join(import.meta.dirname, "..", "src", "validate.mjs");

/**
 * @param {string} input
 * @returns {Promise<{ code: number | null, stdout: string, stderr: string }>}
 */
function run(input) {
	return new Promise((resolve) => {
		const child = execFile(process.execPath, [CLI], (_error, stdout, stderr) => {
			resolve({ code: child.exitCode, stdout, stderr });
		});
		child.stdin?.end(input);
	});
}

describe("validate CLI", () => {
	it("returns findings and counts for a bad script", async () => {
		const { code, stdout } = await run(JSON.stringify({ source: "let x = 1;\nconsole.log(x);", edition: "2014" }));
		expect(code).toBe(0);
		const out = JSON.parse(stdout);
		expect(out.counts.error).toBeGreaterThanOrEqual(2);
		expect(out.findings.map((/** @type {{ ruleId: string }} */ f) => f.ruleId)).toContain("no-restricted-syntax");
	});

	it("returns a clean verdict for valid ES5", async () => {
		const { code, stdout } = await run(JSON.stringify({ source: "var x = 1; console.println(x);", edition: "2014" }));
		expect(code).toBe(0);
		expect(JSON.parse(stdout).counts).toEqual({ error: 0, warning: 0 });
	});

	it("exits nonzero on malformed input", async () => {
		const { code, stderr } = await run("not json");
		expect(code).toBe(1);
		expect(stderr.length).toBeGreaterThan(0);
	});
});

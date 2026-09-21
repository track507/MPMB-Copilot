#!/usr/bin/env node
/**
 * Render the pip-audit and pnpm audit reports as a GitHub step summary
 *
 * Both audits are allowed to exit non-zero when they find something, so their findings never fail the job
 * Printing them here is what keeps a finding visible without downloading an artifact
 *
 * Usage:
 *   node scripts/audit-summary.mjs >> "$GITHUB_STEP_SUMMARY"
 */

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPORTS = path.join(REPO_ROOT, "security-reports");

/**
 * Read one JSON report, or null when it is missing or unparseable
 *
 * @param {string} name
 * @returns {any}
 */
function readReport(name) {
	const file = path.join(REPORTS, name);
	if (!existsSync(file)) return null;
	try {
		return JSON.parse(readFileSync(file, "utf8"));
	} catch {
		return null;
	}
}

/** @returns {string} */
function pipAuditSection() {
	const report = readReport("pip-audit.json");
	if (report === null) return "## pip-audit\n\nNo report produced - the audit did not run\n";

	/** @type {any[]} */
	const deps = Array.isArray(report.dependencies) ? report.dependencies : [];
	const hits = deps.filter((/** @type {any} */ d) => Array.isArray(d.vulns) && d.vulns.length > 0);
	const lines = ["## pip-audit", "", `${deps.length} packages audited, ${hits.length} with advisories`, ""];
	if (hits.length === 0) return lines.join("\n") + "\n";

	lines.push("| package | version | advisories | fixed in |", "| --- | --- | --- | --- |");
	hits.sort((/** @type {any} */ a, /** @type {any} */ b) => b.vulns.length - a.vulns.length);
	for (const dep of hits) {
		const fixes = [...new Set(dep.vulns.flatMap((/** @type {any} */ v) => v.fix_versions ?? []))].sort();
		lines.push(`| ${dep.name} | ${dep.version} | ${dep.vulns.length} | ${fixes.at(-1) ?? "none published"} |`);
	}
	return lines.join("\n") + "\n";
}

/** @returns {string} */
function pnpmAuditSection() {
	const report = readReport("npm-audit.json");
	if (report === null) return "\n## pnpm audit\n\nNo report produced - the audit did not run\n";

	// ? pnpm audit --json reports per-severity counts under metadata.vulnerabilities
	const counts = report.metadata?.vulnerabilities ?? {};
	const found = Object.entries(counts).filter(([, n]) => Number(n) > 0);
	if (found.length === 0) return "\n## pnpm audit\n\nNo advisories at moderate or above\n";

	return `\n## pnpm audit\n\n${found.map(([severity, n]) => `${String(n)} ${severity}`).join(", ")}\n`;
}

process.stdout.write(pipAuditSection() + pnpmAuditSection());

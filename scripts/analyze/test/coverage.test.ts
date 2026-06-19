import { describe, it, expect } from "vitest";
import { buildCoverage } from "../src/coverage";

describe("buildCoverage", () => {
	it("emits CoverageWarning-shaped entries with severities", () => {
		const cov = buildCoverage({ parseErrors: 2, leakCandidates: 5, undeclared: 40, undiscoveredRegistries: 1 });
		const byKey = Object.fromEntries(cov.map((c) => [c.key, c]));
		expect(byKey.parse_errors).toMatchObject({ missed: 2, severity: "high" });
		expect(new Set(Object.keys(byKey))).toEqual(new Set(["parse_errors", "leak_candidates", "undeclared_references", "undiscovered_registries"]));
		for (const c of cov) {
			expect(c).toEqual(
				expect.objectContaining({
					key: expect.any(String),
					label: expect.any(String),
					current: expect.any(Number),
					target: expect.any(Number),
					missed: expect.any(Number),
					severity: expect.stringMatching(/^(low|medium|high)$/),
					description: expect.any(String),
					action: expect.any(String),
				})
			);
		}
	});
});

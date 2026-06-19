import type { CoverageWarning, Severity } from "./types";

export interface CoverageInput {
	parseErrors: number;
	leakCandidates: number;
	undeclared: number;
	undiscoveredRegistries: number;
}

export function buildCoverage(input: CoverageInput): CoverageWarning[] {
	const warn = (key: string, label: string, missed: number, severity: Severity, description: string, action: string): CoverageWarning => ({
		key,
		label,
		current: 0,
		target: 0,
		missed,
		severity,
		description,
		action,
	});

	return [
		warn(
			"parse_errors",
			"Files that failed to parse",
			input.parseErrors,
			"high",
			"Source files acorn could not parse",
			"Inspect the recorded parse errors"
		),
		warn(
			"leak_candidates",
			"Implicit global leak candidates",
			input.leakCandidates,
			"medium",
			"Bare assignments creating new globals not in any known surface",
			"Add var, or confirm as host writes once the host surface lands"
		),
		warn(
			"undeclared_references",
			"Referenced-but-undeclared symbols",
			input.undeclared,
			"low",
			"Symbols used but not declared in source (host-API seed for Subsystem B)",
			"Feed into the host-surface discovery"
		),
		warn(
			"undiscovered_registries",
			"Registries written but not engine-declared",
			input.undiscoveredRegistries,
			"medium",
			"Globals receiving keyed object writes that the engine surface did not declare",
			"Confirm a real registry or a typo'd global"
		),
	];
}

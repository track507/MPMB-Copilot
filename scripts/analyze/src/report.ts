import { classifyImplicit, classifyName } from "./classify";
import { buildCoverage } from "./coverage";
import type { ExtractResult } from "./extract";
import type {
	AddCallEntry,
	AnalysisReport,
	EngineSurface,
	FunctionEntry,
	ImplicitGlobalEntry,
	ObjectEntry,
	ParseErrorEntry,
	ReferenceEntry,
	RepoProvenance,
} from "./types";

export interface BuildReportInput {
	repos: Record<string, RepoProvenance>;
	perFile: ExtractResult[];
	surface: EngineSurface;
	hostSet: Set<string>;
	generatedAt: string;
	projectRoot?: string;
}

export function buildReport(input: BuildReportInput): AnalysisReport {
	const { repos, perFile, surface, hostSet, generatedAt, projectRoot = "." } = input;
	const objects: ObjectEntry[] = [];
	const functions: FunctionEntry[] = [];
	const add_calls: AddCallEntry[] = [];
	const references: ReferenceEntry[] = [];
	const implicit_globals: ImplicitGlobalEntry[] = [];
	const parse_errors: ParseErrorEntry[] = [];
	const undeclaredSeed = new Set<string>();
	const writtenRegistries = new Set<string>();

	for (const f of perFile) {
		if (f.parseError) {
			parse_errors.push({ repo: f.repo, file: f.file, line: f.parseError.line, message: f.parseError.message });
		}
		for (const o of f.objects) {
			objects.push(o);
			writtenRegistries.add(o.object_type);
		}
		for (const fn of f.functions) functions.push(fn);
		for (const c of f.calls) {
			const klass = classifyName(c.callee, surface, hostSet);
			references.push({ repo: c.repo, file: c.file, line: c.line, callee: c.callee, classification: klass });
			// ? record every Add*-convention call; mapped = the engine actually declares it
			if (/^Add[A-Z]/.test(c.callee)) {
				add_calls.push({
					repo: c.repo,
					file: c.file,
					line: c.line,
					function_name: c.callee,
					mapped: surface.addDeclarations.has(c.callee),
				});
			}
			if (klass === "undeclared") undeclaredSeed.add(c.callee);
		}
		for (const g of f.implicitGlobals) {
			implicit_globals.push({
				repo: g.repo,
				file: g.file,
				line: g.line,
				name: g.name,
				classification: classifyImplicit(g.name, surface, hostSet),
			});
		}
		for (const u of f.unresolved) {
			if (classifyName(u.name, surface, hostSet) === "undeclared") undeclaredSeed.add(u.name);
		}
	}

	const undiscoveredRegistries = [...writtenRegistries].filter((r) => !surface.registries.has(r));
	const leakCandidates = implicit_globals.filter((g) => g.classification === "leak-candidate").length;

	return {
		generated_at: generatedAt,
		project_root: projectRoot,
		repos,
		objects,
		add_calls,
		functions,
		coverage_metrics: buildCoverage({
			parseErrors: parse_errors.length,
			leakCandidates,
			undeclared: undeclaredSeed.size,
			undiscoveredRegistries: undiscoveredRegistries.length,
		}),
		source_keys: {},
		required_versions: {},
		// additive (extra="ignore" on the backend)
		discovered_registries: [...surface.registries].sort(),
		all_functions: [...surface.functions.keys()].sort(),
		references,
		implicit_globals,
		undeclared_seed: [...undeclaredSeed].sort(),
		parse_errors,
	};
}

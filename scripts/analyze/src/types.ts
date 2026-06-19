// Types mirroring the backend pydantic CatalogModel (backend/app/model/schemas/source_catalog.py)
// plus internal analyzer types. The contract types are the correctness surface: drift fails tsc.

export type RepoKey = "mpmb_source" | "mpmb_source_2024" | "imports_source";
export type AssignmentKind = "bracket_object" | "function_object" | "dot_object";
export type FunctionKind = "declaration" | "var_function" | "assignment_function";
export type Severity = "low" | "medium" | "high";

export interface RepoProvenance {
	branch: string;
	commit: string;
	short_commit: string;
	date: string;
	subject: string;
	refs: string;
	remote: string;
}

export interface ObjectEntry {
	repo: string;
	file: string;
	line: number;
	object_type: string;
	object_key: string;
	assignment_kind: AssignmentKind;
}

export interface AddCallEntry {
	repo: string;
	file: string;
	line: number;
	function_name: string;
	mapped: boolean;
}

export interface FunctionEntry {
	repo: string;
	file: string;
	line: number;
	name: string;
	kind: FunctionKind;
}

export interface CoverageWarning {
	key: string;
	label: string;
	current: number;
	target: number;
	missed: number;
	severity: Severity;
	description: string;
	action: string;
}

// Exact v1 contract the backend source_catalog validates (extra="ignore").
export interface CatalogModel {
	generated_at: string;
	project_root: string;
	repos: Record<string, RepoProvenance>;
	objects: ObjectEntry[];
	add_calls: AddCallEntry[];
	functions: FunctionEntry[];
	coverage_metrics: CoverageWarning[];
	source_keys: Record<string, number>;
	required_versions: Record<string, Record<string, number>>;
}

// Additive discovery sections (backend ignores them via extra="ignore").
export type ReferenceClass = "engine-fn" | "registry" | "host-API" | "undeclared";
export type ImplicitClass = "host-write" | "leak-candidate";

export interface ReferenceEntry {
	repo: string;
	file: string;
	line: number;
	callee: string;
	classification: ReferenceClass;
}

export interface ImplicitGlobalEntry {
	repo: string;
	file: string;
	line: number;
	name: string;
	classification: ImplicitClass;
}

export interface ParseErrorEntry {
	repo: string;
	file: string;
	line: number;
	message: string;
}

export interface AnalysisReport extends CatalogModel {
	discovered_registries: string[];
	all_functions: string[];
	references: ReferenceEntry[];
	implicit_globals: ImplicitGlobalEntry[];
	undeclared_seed: string[];
	parse_errors: ParseErrorEntry[];
}

// Internal analyzer types.
export interface RepoConfig {
	key: RepoKey;
	dir: string;
	edition: string;
	kind: "mpmb" | "imports";
}

export interface EngineSurface {
	registries: Set<string>;
	functions: Map<string, { arity: number; kind: FunctionKind }>;
	addDeclarations: Set<string>;
}

export interface ParseError {
	line: number;
	message: string;
}

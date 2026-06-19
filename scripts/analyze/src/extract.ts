import * as walk from "acorn-walk";
import { parseFile } from "./parse";
import type { AssignmentKind, FunctionEntry, ObjectEntry, ParseError } from "./types";

type AnyNode = { type: string; [key: string]: unknown };

export interface CallRecord {
	repo: string;
	file: string;
	line: number;
	end_line: number;
	callee: string;
}

export interface ImplicitGlobalRaw {
	repo: string;
	file: string;
	line: number;
	name: string;
}

export interface ExtractResult {
	repo: string;
	file: string;
	objects: ObjectEntry[];
	functions: FunctionEntry[];
	calls: CallRecord[];
	implicitGlobals: ImplicitGlobalRaw[];
	unresolved: { name: string }[];
	parseError: ParseError | null;
}

export interface ExtractMeta {
	repo: string;
	file: string;
	edition: string;
}

function isFn(n: unknown): boolean {
	const node = n as AnyNode | null;
	return !!node && (node.type === "FunctionExpression" || node.type === "ArrowFunctionExpression");
}

function lineOf(node: AnyNode): number {
	const loc = node.loc as { start?: { line?: number } } | undefined;
	return loc?.start?.line ?? 0;
}

function endLineOf(node: AnyNode): number {
	const loc = node.loc as { end?: { line?: number } } | undefined;
	return loc?.end?.line ?? 0;
}

// MemberExpression on a plain Identifier -> { object_type, object_key, dot } | null
function memberTarget(left: AnyNode): { object_type: string; object_key: string; dot: boolean } | null {
	if (left.type !== "MemberExpression") return null;
	const obj = left.object as AnyNode;
	if (obj.type !== "Identifier") return null;
	if (left.computed) {
		const prop = left.property as AnyNode;
		if (prop.type !== "Literal") return null;
		return { object_type: obj.name as string, object_key: String(prop.value), dot: false };
	}
	const prop = left.property as AnyNode;
	return { object_type: obj.name as string, object_key: prop.name as string, dot: true };
}

export function extractFile(code: string, meta: ExtractMeta): ExtractResult {
	const { ast, scopeManager, parseError } = parseFile(code);
	const out: ExtractResult = {
		repo: meta.repo,
		file: meta.file,
		objects: [],
		functions: [],
		calls: [],
		implicitGlobals: [],
		unresolved: [],
		parseError,
	};
	if (!ast) return out;
	const repo = meta.repo;
	const file = meta.file;

	walk.simple(
		ast as never,
		{
			FunctionDeclaration(node: AnyNode) {
				const id = node.id as AnyNode | null;
				if (id) out.functions.push({ repo, file, line: lineOf(node), end_line: endLineOf(node), name: id.name as string, kind: "declaration" });
			},
			VariableDeclarator(node: AnyNode) {
				const id = node.id as AnyNode;
				if (id.type === "Identifier" && isFn(node.init)) {
					out.functions.push({ repo, file, line: lineOf(node), end_line: endLineOf(node), name: id.name as string, kind: "var_function" });
				}
			},
			AssignmentExpression(node: AnyNode) {
				if (node.operator !== "=") return;
				const left = node.left as AnyNode;
				if (left.type === "Identifier" && isFn(node.right)) {
					out.functions.push({
						repo,
						file,
						line: lineOf(node),
						end_line: endLineOf(node),
						name: left.name as string,
						kind: "assignment_function",
					});
					return;
				}
				const t = memberTarget(left);
				if (!t) return;
				const assignment_kind: AssignmentKind = isFn(node.right) ? "function_object" : t.dot ? "dot_object" : "bracket_object";
				out.objects.push({
					repo,
					file,
					line: lineOf(node),
					end_line: endLineOf(node),
					object_type: t.object_type,
					object_key: t.object_key,
					assignment_kind,
				});
			},
			CallExpression(node: AnyNode) {
				const callee = node.callee as AnyNode;
				if (callee.type === "Identifier") out.calls.push({ repo, file, line: lineOf(node), end_line: endLineOf(node), callee: callee.name as string });
			},
		} as never
	);

	// Scope facts: implicit globals (bare writes, no var) + all unresolved references
	const global = scopeManager?.globalScope as
		| { implicit?: { variables?: Array<{ name: string; identifiers?: AnyNode[] }> }; through?: Array<{ identifier?: AnyNode }> }
		| undefined;
	if (global) {
		for (const v of global.implicit?.variables ?? []) {
			const id = v.identifiers?.[0];
			out.implicitGlobals.push({ repo, file, line: id ? lineOf(id) : 0, name: v.name });
		}
		const seen = new Set<string>();
		for (const ref of global.through ?? []) {
			const name = ref.identifier?.name as string | undefined;
			if (name && !seen.has(name)) {
				seen.add(name);
				out.unresolved.push({ name });
			}
		}
	}
	return out;
}

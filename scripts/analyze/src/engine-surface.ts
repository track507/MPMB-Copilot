import * as walk from "acorn-walk";
import { parseFile } from "./parse";
import type { EngineSurface, FunctionKind } from "./types";

// AST node typing across acorn/estree/acorn-walk is fiddly; keep traversal loose and the returned EngineSurface strictly typed
type AnyNode = { type: string; [key: string]: unknown };

function isFn(n: unknown): boolean {
	const node = n as AnyNode | null;
	return !!node && (node.type === "FunctionExpression" || node.type === "ArrowFunctionExpression");
}

// ? object container: {} or X || {} or nested logical of those
function isObjectish(n: unknown): boolean {
	const node = n as AnyNode | null;
	if (!node) return false;
	if (node.type === "ObjectExpression") return true;
	if (node.type === "LogicalExpression") return isObjectish(node.left) || isObjectish(node.right);
	return false;
}

function paramCount(fn: unknown): number {
	return ((fn as AnyNode).params as unknown[]).length;
}

export function buildEngineSurface(codes: string[]): EngineSurface {
	const registries = new Set<string>();
	const functions = new Map<string, { arity: number; kind: FunctionKind }>();

	for (const code of codes) {
		const { ast } = parseFile(code);
		if (!ast) continue;
		walk.simple(
			ast as never,
			{
				FunctionDeclaration(node: AnyNode) {
					const id = node.id as AnyNode | null;
					if (id) functions.set(id.name as string, { arity: paramCount(node), kind: "declaration" });
				},
				VariableDeclarator(node: AnyNode) {
					const id = node.id as AnyNode;
					if (id.type !== "Identifier") return;
					if (isFn(node.init)) functions.set(id.name as string, { arity: paramCount(node.init), kind: "var_function" });
					else if (isObjectish(node.init)) registries.add(id.name as string);
				},
				AssignmentExpression(node: AnyNode) {
					const left = node.left as AnyNode;
					if (node.operator !== "=" || left.type !== "Identifier") return;
					if (isFn(node.right)) {
						functions.set(left.name as string, { arity: paramCount(node.right), kind: "assignment_function" });
					} else if (isObjectish(node.right)) {
						registries.add(left.name as string);
					}
				},
			} as never
		);
	}

	// ! Add* is a derived convention over discovered engine functions, never a hardcoded list
	const addDeclarations = new Set([...functions.keys()].filter((n) => /^Add[A-Z]/.test(n)));
	return { registries, functions, addDeclarations };
}

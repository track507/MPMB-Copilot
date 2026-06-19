import { parse as acornParse } from "acorn";
import * as eslintScope from "eslint-scope";
import type { ScopeManager } from "eslint-scope";
import type { Program } from "estree";
import type { ParseError } from "./types";

// ! Permissive for discovery; ES5 enforcement is the validator's job (Subsystem C)
const ECMA_VERSION = 2022;

export interface ParseResult {
	ast: Program | null;
	scopeManager: ScopeManager | null;
	parseError: ParseError | null;
}

export function parseFile(code: string): ParseResult {
	try {
		const ast = acornParse(code, {
			ecmaVersion: ECMA_VERSION,
			sourceType: "script",
			locations: true,
			ranges: true, // ! eslint-scope needs node.range (it targets espree, which sets it)
			allowReturnOutsideFunction: true, // ? AcroJS globalReturn
		}) as unknown as Program;
		const scopeManager = eslintScope.analyze(ast as never, {
			ecmaVersion: ECMA_VERSION,
			sourceType: "script",
		});
		return { ast, scopeManager, parseError: null };
	} catch (err) {
		const e = err as { loc?: { line: number }; message?: string };
		return {
			ast: null,
			scopeManager: null,
			parseError: { line: e.loc?.line ?? 0, message: String(e.message) },
		};
	}
}

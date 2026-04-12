import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
	{ ignores: ["**/node_modules/**", "**/dist/**"] },

	{ ...js.configs.recommended },

	// Non-React TypeScript files (.ts)
	{
		files: ["**/*.ts"],
		extends: [...tseslint.configs.strictTypeChecked, ...tseslint.configs.stylisticTypeChecked],
		languageOptions: {
			globals: { ...globals.node },
			parserOptions: {
				projectService: true,
				tsconfigRootDir: import.meta.dirname,
			},
		},
		rules: {
			"@typescript-eslint/naming-convention": [
				"error",
				{ selector: "interface", format: ["PascalCase"] },
				{ selector: "typeAlias", format: ["PascalCase"] },
				{ selector: "class", format: ["PascalCase"] },
				{ selector: "enum", format: ["PascalCase"] },
				{ selector: "enumMember", format: ["PascalCase", "UPPER_CASE"] },
				{ selector: "variable", format: ["camelCase", "UPPER_CASE", "PascalCase"], leadingUnderscore: "allow" },
				{ selector: "function", format: ["camelCase", "PascalCase"] },
				{ selector: "parameter", format: ["camelCase"], leadingUnderscore: "allow" },
				{ selector: "method", format: ["camelCase"] },
				{ selector: "property", format: ["camelCase", "PascalCase", "UPPER_CASE", "snake_case"], leadingUnderscore: "allow" },
				{ selector: "property", format: null, modifiers: ["requiresQuotes"] },
			],
			"@typescript-eslint/explicit-function-return-type": ["error", { allowExpressions: true, allowTypedFunctionExpressions: true }],
			"@typescript-eslint/explicit-module-boundary-types": "error",
			"@typescript-eslint/no-floating-promises": "error",
			"@typescript-eslint/await-thenable": "error",
			"@typescript-eslint/no-misused-promises": "error",
			"@typescript-eslint/promise-function-async": "error",
			"@typescript-eslint/no-confusing-void-expression": "error",
			"@typescript-eslint/no-explicit-any": "error",
			"@typescript-eslint/no-non-null-assertion": "error",
			"@typescript-eslint/strict-boolean-expressions": "error",
			"@typescript-eslint/prefer-nullish-coalescing": "error",
			"@typescript-eslint/prefer-optional-chain": "error",
			"@typescript-eslint/no-unnecessary-condition": "error",
			"@typescript-eslint/switch-exhaustiveness-check": "error",
			"@typescript-eslint/prefer-readonly": "error",
			"@typescript-eslint/no-unsafe-argument": "error",
			"@typescript-eslint/no-unsafe-assignment": "error",
			"@typescript-eslint/no-unsafe-call": "error",
			"@typescript-eslint/no-unsafe-member-access": "error",
			"@typescript-eslint/no-unsafe-return": "error",
			"@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports", fixStyle: "separate-type-imports" }],
			"@typescript-eslint/no-import-type-side-effects": "error",
			"@typescript-eslint/array-type": ["error", { default: "array-simple" }],
			"no-unused-vars": "off",
			"no-undef": "off",
			"no-console": "error",
			eqeqeq: ["error", "always"],
			"no-var": "error",
			"prefer-const": "error",
			"no-param-reassign": "error",
		},
	},

	// React/TSX files
	{
		files: ["**/*.tsx"],
		extends: [
			...tseslint.configs.strictTypeChecked,
			...tseslint.configs.stylisticTypeChecked,
			reactHooks.configs.flat.recommended,
			reactRefresh.configs.vite,
		],
		languageOptions: {
			globals: { ...globals.browser },
			parserOptions: {
				projectService: true,
				tsconfigRootDir: import.meta.dirname,
				ecmaFeatures: { jsx: true },
			},
		},
		rules: {
			"@typescript-eslint/naming-convention": [
				"error",
				{ selector: "interface", format: ["PascalCase"] },
				{ selector: "typeAlias", format: ["PascalCase"] },
				{ selector: "class", format: ["PascalCase"] },
				{ selector: "enum", format: ["PascalCase"] },
				{ selector: "enumMember", format: ["PascalCase", "UPPER_CASE"] },
				{ selector: "variable", format: ["camelCase", "UPPER_CASE", "PascalCase"], leadingUnderscore: "allow" },
				{ selector: "function", format: ["camelCase", "PascalCase"] },
				{ selector: "parameter", format: ["camelCase"], leadingUnderscore: "allow" },
				{ selector: "method", format: ["camelCase"] },
				{ selector: "property", format: ["camelCase", "PascalCase", "UPPER_CASE", "snake_case"], leadingUnderscore: "allow" },
				{ selector: "property", format: null, modifiers: ["requiresQuotes"] },
			],
			"@typescript-eslint/explicit-function-return-type": ["error", { allowExpressions: true, allowTypedFunctionExpressions: true }],
			"@typescript-eslint/explicit-module-boundary-types": "error",
			"@typescript-eslint/no-floating-promises": "error",
			"@typescript-eslint/await-thenable": "error",
			"@typescript-eslint/no-misused-promises": "error",
			"@typescript-eslint/promise-function-async": "error",
			"@typescript-eslint/no-confusing-void-expression": "error",
			"@typescript-eslint/no-explicit-any": "error",
			"@typescript-eslint/no-non-null-assertion": "error",
			"@typescript-eslint/strict-boolean-expressions": "error",
			"@typescript-eslint/prefer-nullish-coalescing": "error",
			"@typescript-eslint/prefer-optional-chain": "error",
			"@typescript-eslint/no-unnecessary-condition": "error",
			"@typescript-eslint/switch-exhaustiveness-check": "error",
			"@typescript-eslint/prefer-readonly": "error",
			"@typescript-eslint/no-unsafe-argument": "error",
			"@typescript-eslint/no-unsafe-assignment": "error",
			"@typescript-eslint/no-unsafe-call": "error",
			"@typescript-eslint/no-unsafe-member-access": "error",
			"@typescript-eslint/no-unsafe-return": "error",
			"@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports", fixStyle: "separate-type-imports" }],
			"@typescript-eslint/no-import-type-side-effects": "error",
			"@typescript-eslint/array-type": ["error", { default: "array-simple" }],
			"no-unused-vars": "off",
			"no-undef": "off",
			"no-console": "warn",
			eqeqeq: ["error", "always"],
			"no-var": "error",
			"prefer-const": "error",
			"no-param-reassign": "error",
		},
	},

	// shadcn/ui generated components - relax rules since these are vendored.
	// Glob matches both `src/...` (when run from frontend/) and
	// `frontend/src/...` (when lint-staged runs from project root).
	{
		files: ["**/components/ui/**/*.{ts,tsx}"],
		rules: {
			"@typescript-eslint/naming-convention": "off",
			"@typescript-eslint/explicit-function-return-type": "off",
			"@typescript-eslint/explicit-module-boundary-types": "off",
			"react-refresh/only-export-components": "off",
		},
	}
);

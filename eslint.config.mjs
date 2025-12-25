// ESLint Flat Config for Adobe Acrobat JavaScript (ECMAScript 5)
// Adobe PDF scripting uses ES5 with proprietary extensions
import js from "@eslint/js";

export default [
	// Global ignores
	{
		ignores: ["**/.git/**", "**/*.min.js"],
	},

	// Base recommended rules
	js.configs.recommended,

	// Configuration for Adobe Acrobat JavaScript files
	{
		files: ["**/*.js"],

		languageOptions: {
			ecmaVersion: 5,
			sourceType: "script", // Adobe uses script mode, not module

			globals: {
				// Adobe Acrobat JavaScript API globals
				// Document level
				app: "readonly",
				doc: "readonly",
				event: "readonly",

				// Console (Adobe uses console.println, not console.log)
				console: "readonly",

				// Utility objects
				util: "readonly",
				color: "readonly",
				border: "readonly",
				display: "readonly",
				font: "readonly",
				highlight: "readonly",
				position: "readonly",
				scaleHow: "readonly",
				scaleWhen: "readonly",
				style: "readonly",
				zoomtype: "readonly",

				// SOAP and Security
				SOAP: "readonly",
				SOAPEnvelope: "readonly",
				security: "readonly",

				// Spell check
				spell: "readonly",

				// Global functions
				AFMergeChange: "readonly",
				AFParseDateEx: "readonly",
				AFExtractNums: "readonly",
				AFMakeNumber: "readonly",
				AFSimple: "readonly",
				AFSimple_Calculate: "readonly",
				AFPercent_Format: "readonly",
				AFPercent_Keystroke: "readonly",
				AFDate_Format: "readonly",
				AFDate_FormatEx: "readonly",
				AFDate_Keystroke: "readonly",
				AFDate_KeystrokeEx: "readonly",
				AFTime_Format: "readonly",
				AFTime_Keystroke: "readonly",
				AFTime_FormatEx: "readonly",
				AFTime_KeystrokeEx: "readonly",
				AFSpecial_Format: "readonly",
				AFSpecial_Keystroke: "readonly",
				AFSpecial_KeystrokeEx: "readonly",
				AFNumber_Format: "readonly",
				AFNumber_Keystroke: "readonly",
				AFRange_Validate: "readonly",

				// Other common globals
				Math: "readonly",
				String: "readonly",
				Number: "readonly",
				Boolean: "readonly",
				Array: "readonly",
				Date: "readonly",
				RegExp: "readonly",
				Object: "readonly",
				Function: "readonly",
				Error: "readonly",
				EvalError: "readonly",
				RangeError: "readonly",
				ReferenceError: "readonly",
				SyntaxError: "readonly",
				TypeError: "readonly",
				URIError: "readonly",

				// Standard global functions
				parseInt: "readonly",
				parseFloat: "readonly",
				isNaN: "readonly",
				isFinite: "readonly",
				decodeURI: "readonly",
				decodeURIComponent: "readonly",
				encodeURI: "readonly",
				encodeURIComponent: "readonly",
				escape: "readonly",
				unescape: "readonly",

				// Undefined/null
				undefined: "readonly",
				NaN: "readonly",
				Infinity: "readonly",
			},

			parserOptions: {
				ecmaFeatures: {
					impliedStrict: false, // ES5 doesn't use strict mode by default
					globalReturn: true,
				},
			},
		},

		rules: {
			// Prevent modern JavaScript features not available in ES5
			"no-const-assign": "off", // const doesn't exist in ES5
			"no-var": "off", // var is required in ES5
			"prefer-const": "off", // const doesn't exist in ES5
			"prefer-arrow-callback": "off", // Arrow functions don't exist in ES5
			"prefer-template": "off", // Template literals don't exist in ES5
			"object-shorthand": "off", // ES6 object shorthand not available
			"prefer-destructuring": "off", // Destructuring doesn't exist in ES5
			"prefer-rest-params": "off", // Rest parameters don't exist in ES5
			"prefer-spread": "off", // Spread operator doesn't exist in ES5

			// Bug prevention
			"no-debugger": "error",
			"no-duplicate-imports": "off", // No imports in ES5
			"no-self-compare": "error",
			"no-template-curly-in-string": "off", // No template literals in ES5
			"no-unreachable-loop": "error",
			"no-unused-vars": [
				"warn",
				{
					vars: "all",
					args: "after-used",
					argsIgnorePattern: "^_",
					varsIgnorePattern: "^_",
				},
			],
			"require-atomic-updates": "off", // async/await doesn't exist in ES5

			// Code quality
			eqeqeq: ["error", "always", { null: "ignore" }],
			"no-eval": "error",
			"no-implied-eval": "error",
			"no-new-func": "error",
			"no-throw-literal": "error",
			"no-new-wrappers": "error",
			"no-script-url": "error",
			"no-sequences": "warn",
			"array-callback-return": "error",
			"no-empty": ["error", { allowEmptyCatch: true }],
			"no-lonely-if": "warn",

			// Adobe-specific restrictions
			"no-restricted-globals": [
				"error",
				{
					name: "eval",
					message: "eval() should be avoided for security reasons",
				},
			],

			"no-restricted-properties": [
				"error",
				{
					object: "console",
					property: "log",
					message: "Adobe uses console.println() instead of console.log()",
				},
				{
					object: "console",
					property: "error",
					message: "Adobe uses console.println() for all console output",
				},
				{
					object: "console",
					property: "warn",
					message: "Adobe uses console.println() for all console output",
				},
				{
					object: "console",
					property: "info",
					message: "Adobe uses console.println() for all console output",
				},
				{
					object: "console",
					property: "debug",
					message: "Adobe uses console.println() for all console output",
				},
				{
					object: "Array",
					property: "from",
					message: "Array.from() is ES6. Use Array.prototype.slice.call() instead",
				},
				{
					object: "Object",
					property: "assign",
					message: "Object.assign() is ES6. Use manual property copying instead",
				},
				{
					object: "Promise",
					message: "Promises are not available in Adobe JavaScript",
				},
			],

			"no-restricted-syntax": [
				"error",
				{
					selector: "ArrowFunctionExpression",
					message: "Arrow functions are not available in ES5. Use function expressions instead.",
				},
				{
					selector: "VariableDeclaration[kind='const']",
					message: "const is not available in ES5. Use var instead.",
				},
				{
					selector: "VariableDeclaration[kind='let']",
					message: "let is not available in ES5. Use var instead.",
				},
				{
					selector: "TemplateLiteral",
					message: "Template literals are not available in ES5. Use string concatenation instead.",
				},
				{
					selector: "ClassDeclaration",
					message: "Classes are not available in ES5. Use function constructors instead.",
				},
				{
					selector: "ForOfStatement",
					message:
						"for...of loops are not available in ES5. Use for loops or Array.prototype.forEach instead.",
				},
				{
					selector: "SpreadElement",
					message: "Spread operator is not available in ES5.",
				},
				{
					selector: "RestElement",
					message: "Rest parameters are not available in ES5. Use arguments object instead.",
				},
				{
					selector: "Property[method=true]",
					message: "Method shorthand is not available in ES5. Use function expressions instead.",
				},
				{
					selector: "Property[shorthand=true]",
					message: "Object property shorthand is not available in ES5. Use full property syntax.",
				},
			],
		},
	},
];

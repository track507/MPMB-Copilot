// AcroJS flat-config builder for the programmatic Linter
// ! Deliberately NOT named eslint.config.mjs: ESLint v10 resolves the nearest config per linted file, and a config by that name would hijack repo-wide `eslint .` runs
import js from "@eslint/js";

// * ES5 builtins per the ES5.1 spec
const ES5_BUILTINS = /** @type {Record<string, "readonly" | "writable">} */ (
	Object.fromEntries(
		[
			"Math",
			"String",
			"Number",
			"Boolean",
			"Array",
			"Date",
			"RegExp",
			"Object",
			"Function",
			"Error",
			"EvalError",
			"RangeError",
			"ReferenceError",
			"SyntaxError",
			"TypeError",
			"URIError",
			"JSON",
			"eval",
			"parseInt",
			"parseFloat",
			"isNaN",
			"isFinite",
			"decodeURI",
			"decodeURIComponent",
			"encodeURI",
			"encodeURIComponent",
			"escape",
			"unescape",
			"undefined",
			"NaN",
			"Infinity",
		].map((name) => [name, "readonly"])
	)
);

// * Acrobat host objects and AF format functions
const ACROBAT_HOST = /** @type {Record<string, "readonly" | "writable">} */ (
	Object.fromEntries(
		[
			"app",
			"doc",
			"event",
			"console",
			"util",
			"global",
			"color",
			"border",
			"display",
			"font",
			"highlight",
			"position",
			"scaleHow",
			"scaleWhen",
			"style",
			"zoomtype",
			"SOAP",
			"SOAPEnvelope",
			"security",
			"spell",
			"AFMergeChange",
			"AFParseDateEx",
			"AFExtractNums",
			"AFMakeNumber",
			"AFSimple",
			"AFSimple_Calculate",
			"AFPercent_Format",
			"AFPercent_Keystroke",
			"AFDate_Format",
			"AFDate_FormatEx",
			"AFDate_Keystroke",
			"AFDate_KeystrokeEx",
			"AFTime_Format",
			"AFTime_Keystroke",
			"AFTime_FormatEx",
			"AFTime_KeystrokeEx",
			"AFSpecial_Format",
			"AFSpecial_Keystroke",
			"AFSpecial_KeystrokeEx",
			"AFNumber_Format",
			"AFNumber_Keystroke",
			"AFRange_Validate",
		].map((name) => [name, "readonly"])
	)
);

// * Parse as modern JS, ban everything newer than ES5 below: ecmaVersion 5 would reject the same code with opaque parse errors instead of these teaching messages
const ES6_BANS = [
	{ selector: "ArrowFunctionExpression", message: "Arrow functions are not available in ES5. Use function expressions instead." },
	{ selector: "VariableDeclaration[kind='const']", message: "const is not available in ES5. Use var instead." },
	{ selector: "VariableDeclaration[kind='let']", message: "let is not available in ES5. Use var instead." },
	{ selector: "TemplateLiteral", message: "Template literals are not available in ES5. Use string concatenation instead." },
	{ selector: "ClassDeclaration, ClassExpression", message: "Classes are not available in ES5. Use function constructors instead." },
	{ selector: "ForOfStatement", message: "for...of is not available in ES5. Use a plain for loop instead." },
	{ selector: "SpreadElement", message: "The spread operator is not available in ES5. Use concat/apply instead." },
	{ selector: "RestElement", message: "Rest parameters are not available in ES5. Use the arguments object instead." },
	{ selector: "Property[method=true]", message: "Method shorthand is not available in ES5. Use key: function () {} instead." },
	{ selector: "Property[shorthand=true]", message: "Property shorthand is not available in ES5. Write the key and value explicitly." },
	{ selector: "Property[computed=true]", message: "Computed property keys are not available in ES5. Assign the key after creating the object." },
	{ selector: ":function[async=true]", message: "async/await is not available in ES5." },
	{ selector: "AwaitExpression", message: "async/await is not available in ES5." },
	{ selector: ":function[generator=true]", message: "Generators are not available in ES5." },
	{ selector: "YieldExpression", message: "Generators are not available in ES5." },
	{ selector: "ObjectPattern, ArrayPattern", message: "Destructuring is not available in ES5. Read properties and elements individually." },
	{ selector: "AssignmentPattern", message: "Default parameters are not available in ES5. Check for undefined inside the function." },
	{
		selector: "BinaryExpression[operator='**'], AssignmentExpression[operator='**=']",
		message: "The exponentiation operator is not available in ES5. Use Math.pow() instead.",
	},
	{ selector: "ChainExpression", message: "Optional chaining (?.) is not available in ES5. Check each level explicitly." },
	{
		selector:
			"LogicalExpression[operator='??'], AssignmentExpression[operator='??='], AssignmentExpression[operator='||='], AssignmentExpression[operator='&&=']",
		message: "Nullish and logical assignment operators are not available in ES5.",
	},
	{ selector: "Literal[regex.flags=/[uvsy]/]", message: "Regex flags beyond g, i, and m are not available in ES5." },
];

const RESTRICTED_PROPERTIES = [
	{ object: "console", property: "log", message: "Adobe uses console.println() instead of console.log()" },
	{ object: "console", property: "error", message: "Adobe uses console.println() for all console output" },
	{ object: "console", property: "warn", message: "Adobe uses console.println() for all console output" },
	{ object: "console", property: "info", message: "Adobe uses console.println() for all console output" },
	{ object: "console", property: "debug", message: "Adobe uses console.println() for all console output" },
	{ object: "Array", property: "from", message: "Array.from() is ES6. Use Array.prototype.slice.call() instead" },
	{ object: "Object", property: "assign", message: "Object.assign() is ES6. Copy properties manually instead" },
	{ object: "Promise", message: "Promises are not available in Adobe JavaScript" },
];

/** @type {import("eslint").Linter.Config["rules"]} */
const RULES = {
	...js.configs.recommended.rules,

	// hard failures: these break in Acrobat's engine or reference unknown names
	"no-restricted-syntax": ["error", ...ES6_BANS],
	"no-restricted-properties": ["error", ...RESTRICTED_PROPERTIES],
	"no-undef": "error",
	"no-debugger": "error",

	// modern-preference rules make no sense against an ES5 target
	"no-var": "off",
	"prefer-const": "off",
	"prefer-arrow-callback": "off",
	"prefer-template": "off",
	"object-shorthand": "off",
	"prefer-destructuring": "off",
	"prefer-rest-params": "off",
	"prefer-spread": "off",

	// quality signals stay warnings: the engine corpus uses these idioms and the corpus gate counts errors only
	"no-unused-vars": ["warn", { vars: "all", args: "after-used", argsIgnorePattern: "^_", varsIgnorePattern: "^_|^iFileName$" }],
	eqeqeq: ["warn", "always", { null: "ignore" }],
	"no-eval": "warn",
	"no-implied-eval": "warn",
	"no-new-func": "warn",
	"no-throw-literal": "warn",
	"no-new-wrappers": "warn",
	"no-script-url": "warn",
	"no-sequences": "warn",
	"array-callback-return": "warn",
	"no-empty": ["warn", { allowEmptyCatch: true }],
	"no-lonely-if": "warn",
	"no-self-compare": "warn",
	"no-unreachable-loop": "warn",
	"no-template-curly-in-string": "warn",

	// ? corpus-driven downgrades: the shipped engine uses these idioms and they run fine in Acrobat
	"no-redeclare": "warn", // ? 1529x: repeated var declarations of the same name
	"no-useless-escape": "warn", // ? 195x: over-escaped regexes and strings
	"no-fallthrough": "warn", // ? 106x: intentional switch fallthrough
	"no-useless-assignment": "warn", // ? 98x: dead stores
	"no-dupe-keys": "warn", // ? 12x in shipped content; ES5 is last-key-wins
	"no-cond-assign": "warn", // ? while ((m = rx.exec(str))) loops
	"no-self-assign": ["warn", { props: false }], // ? Fld.value = Fld.value re-renders a field; the property form must not be flagged at all
	"no-regex-spaces": "warn",
	"no-control-regex": "warn",
	"no-unreachable": "warn",
	"no-dupe-else-if": "warn",
	"no-unused-labels": "warn",
};

/** @typedef {import("./generate-globals.mjs").GlobalsSets} GlobalsSets */
/** @typedef {import("./generate-globals.mjs").Edition} Edition */

/**
 * @param {Edition} edition
 * @param {GlobalsSets} globalsData
 * @returns {import("eslint").Linter.Config}
 */
export function buildConfig(edition, globalsData) {
	/** @type {Record<string, "readonly" | "writable">} */
	const globals = { ...ES5_BUILTINS, ...ACROBAT_HOST };
	// * writable: the engine sources assign these bindings themselves; readonly would fail the corpus gate
	for (const name of [...(globalsData.common ?? []), ...(globalsData[edition] ?? [])]) globals[name] = "writable";
	return {
		languageOptions: {
			ecmaVersion: "latest",
			sourceType: "script",
			parserOptions: { ecmaFeatures: { impliedStrict: false, globalReturn: true } },
			globals,
		},
		rules: RULES,
	};
}

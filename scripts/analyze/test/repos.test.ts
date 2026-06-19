import { describe, it, expect } from "vitest";
import { isSkippedFile, REPOS, SKIP_NAMES } from "../src/repos";

describe("repos", () => {
	it("repo keys match the catalog contract Literal", () => {
		expect(REPOS.map((r) => r.key)).toEqual(["mpmb_source", "mpmb_source_2024", "imports_source"]);
	});

	it("maps editions and engine kind", () => {
		expect(REPOS[0]).toMatchObject({ edition: "2014", kind: "mpmb" });
		expect(REPOS[2]).toMatchObject({ edition: "auto", kind: "imports" });
	});

	it("skips build files", () => {
		expect(SKIP_NAMES.has("gulpfile.js")).toBe(true);
		expect(SKIP_NAMES.has("package.json")).toBe(true);
	});

	it("skips minified WotC bundles but keeps real sources", () => {
		expect(isSkippedFile("WotC material/all_WotC_pub+UA.min.js")).toBe(true);
		expect(isSkippedFile("some/path/vendor.min.js")).toBe(true);
		expect(isSkippedFile("gulpfile.js")).toBe(true);
		expect(isSkippedFile("WotC material/pub_20181120_GGtR.js")).toBe(false);
		expect(isSkippedFile("_functions/Functions1.js")).toBe(false);
	});
});

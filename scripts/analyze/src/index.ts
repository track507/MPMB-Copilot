import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { buildEngineSurface } from "./engine-surface";
import { extractFile } from "./extract";
import type { ExtractMeta, ExtractResult } from "./extract";
import { buildReport } from "./report";
import { gitProvenance, listFiles, REPOS } from "./repos";
import type { RepoProvenance } from "./types";

// ? Resolve paths against the repo root, not the cwd (pnpm --filter runs from the package dir)
const ROOT = path.resolve(import.meta.dirname, "../../..");
const OUT = path.join(ROOT, "scripts", "analyze", "reports", "mpmb-analysis.json");

async function loadHostSet(): Promise<Set<string>> {
	const idx = process.argv.indexOf("--host-symbols");
	const file = idx === -1 ? undefined : process.argv[idx + 1];
	if (!file) return new Set();
	const raw = await readFile(file, "utf8");
	return new Set(JSON.parse(raw) as string[]);
}

async function main(): Promise<void> {
	const hostSet = await loadHostSet();
	const repos: Record<string, RepoProvenance> = {};
	const engineCodes: string[] = [];
	const perFile: ExtractResult[] = [];
	const engineCodesByRepo = new Map<string, string[]>();

	for (const repo of REPOS) {
		const dir = path.join(ROOT, repo.dir);
		repos[repo.key] = gitProvenance(dir);
		const files = await listFiles(dir);
		for (const rel of files) {
			let code: string;
			try {
				code = await readFile(path.join(dir, rel), "utf8");
			} catch {
				continue;
			}
			if (repo.kind === "mpmb") {
				engineCodes.push(code);
				const bucket = engineCodesByRepo.get(repo.key) ?? [];
				bucket.push(code);
				engineCodesByRepo.set(repo.key, bucket);
			}
			const meta: ExtractMeta = { repo: repo.key, file: rel, edition: repo.edition };
			perFile.push(extractFile(code, meta));
		}
	}

	const surface = buildEngineSurface(engineCodes);
	const surfacesByRepo = Object.fromEntries([...engineCodesByRepo].map(([key, codes]) => [key, buildEngineSurface(codes)]));
	const report = buildReport({
		repos,
		perFile,
		surface,
		hostSet,
		generatedAt: new Date().toISOString(),
		projectRoot: ".",
		surfacesByRepo,
	});

	await mkdir(path.dirname(OUT), { recursive: true });
	await writeFile(OUT, JSON.stringify(report, null, 2) + "\n", "utf8");
	console.log(
		`Wrote ${OUT}: ${report.objects.length} objects, ${report.functions.length} functions, ` +
			`${report.add_calls.length} add_calls, ${report.discovered_registries.length} registries, ` +
			`${report.implicit_globals.length} implicit-globals, ${report.undeclared_seed.length} undeclared-seed`
	);
}

main().catch((err: unknown) => {
	console.error(err);
	process.exitCode = 1;
});

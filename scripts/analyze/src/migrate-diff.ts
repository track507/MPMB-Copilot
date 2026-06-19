import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

type Row = Record<string, unknown>;
type Catalog = { objects?: Row[]; add_calls?: Row[]; functions?: Row[] };

const KEYS: Record<string, (r: Row) => string> = {
	objects: (o) => `${o.repo}|${o.file}|${o.object_type}|${o.object_key}`,
	add_calls: (c) => `${c.repo}|${c.file}|${c.function_name}`,
	functions: (f) => `${f.repo}|${f.file}|${f.name}`,
};

export interface DiffResult {
	missingInNew: Record<string, Row[]>;
	newOnly: Record<string, Row[]>;
}

export function diffCatalogs(oldCat: Catalog, newCat: Catalog): DiffResult {
	const missingInNew: Record<string, Row[]> = {};
	const newOnly: Record<string, Row[]> = {};
	for (const [coll, keyOf] of Object.entries(KEYS)) {
		const oldRows = (oldCat[coll as keyof Catalog] ?? []) as Row[];
		const newRows = (newCat[coll as keyof Catalog] ?? []) as Row[];
		const oldKeys = new Set(oldRows.map(keyOf));
		const newKeys = new Set(newRows.map(keyOf));
		missingInNew[coll] = oldRows.filter((x) => !newKeys.has(keyOf(x)));
		newOnly[coll] = newRows.filter((x) => !oldKeys.has(keyOf(x)));
	}
	return { missingInNew, newOnly };
}

// CLI: diffs reports/old-baseline.json (the Python snapshot) vs reports/mpmb-analysis.json (the new run)
async function cli(): Promise<void> {
	const root = path.resolve(import.meta.dirname, "../../..");
	const reports = path.join(root, "scripts", "analyze", "reports");
	const oldCat = JSON.parse(await readFile(path.join(reports, "old-baseline.json"), "utf8")) as Catalog;
	const newCat = JSON.parse(await readFile(path.join(reports, "mpmb-analysis.json"), "utf8")) as Catalog;
	const d = diffCatalogs(oldCat, newCat);
	for (const coll of ["objects", "add_calls", "functions"]) {
		console.log(`${coll}: missing-in-new=${d.missingInNew[coll].length}  new-only=${d.newOnly[coll].length}`);
	}
	for (const coll of ["objects", "add_calls", "functions"]) {
		const sample = d.missingInNew[coll].slice(0, 6);
		if (sample.length) console.log(`  sample missing ${coll}:`, JSON.stringify(sample));
	}
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
	cli().catch((err: unknown) => {
		console.error(err);
		process.exitCode = 1;
	});
}

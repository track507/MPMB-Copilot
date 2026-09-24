#!/usr/bin/env node
/**
 * Stamp tenant_id onto vectors indexed before the tenant filter existed
 *
 * Retrieval now requires tenant_id IN (caller, "_shared") on every point
 * Points indexed earlier carry no such field, so they match nothing and search silently returns empty
 * Re-indexing would also fix it, but this is one API call against payloads rather than an hour of embedding
 *
 * A fresh install never needs this: the indexer stamps _shared as it writes
 *
 * Usage:
 *   node scripts/backfill-tenant-payload.mjs            dry run, reports what would change
 *   node scripts/backfill-tenant-payload.mjs --apply    performs the update
 */

import process from "node:process";

const SHARED_TENANT = "_shared";
const QDRANT = process.env.QDRANT_URL ?? "http://127.0.0.1:6333";
const COLLECTION = process.env.QDRANT_COLLECTION ?? "mpmb_code";
const apply = process.argv.includes("--apply");

/**
 * @param {string} path
 * @param {unknown} body
 * @returns {Promise<any>}
 */
async function qdrant(path, body) {
	const res = await fetch(`${QDRANT}${path}`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body),
	});
	if (!res.ok) throw new Error(`${path} -> ${res.status} ${await res.text()}`);
	/** @type {any} */
	const body_ = await res.json();
	return body_.result;
}

/**
 * @param {unknown} filter
 * @returns {Promise<number>}
 */
async function countWhere(filter) {
	/** @type {{ count: number }} */
	const { count } = await qdrant(`/collections/${COLLECTION}/points/count`, { filter, exact: true });
	return count;
}

async function main() {
	const total = await countWhere(undefined);
	const tagged = await countWhere({ must: [{ key: "tenant_id", match: { any: [SHARED_TENANT] } }] });

	console.log(`Collection: ${COLLECTION} at ${QDRANT}`);
	console.log(`  points total:            ${total}`);
	console.log(`  already tenant-stamped:  ${tagged}`);
	console.log(`  would be stamped shared: ${total - tagged}`);

	if (total === tagged) {
		console.log("\nNothing to do.");
		return 0;
	}
	if (!apply) {
		console.log("\nDry run. Re-run with --apply to stamp them.");
		return 0;
	}

	await qdrant(`/collections/${COLLECTION}/points/payload?wait=true`, {
		payload: { tenant_id: SHARED_TENANT },
		filter: {},
	});

	const after = await countWhere({ must: [{ key: "tenant_id", match: { any: [SHARED_TENANT] } }] });
	console.log(`\nStamped. Points now visible to every tenant: ${after} of ${total}`);
	if (after !== total) {
		console.error("Some points were not stamped; investigate before trusting search.");
		return 1;
	}
	return 0;
}

process.exitCode = await main();

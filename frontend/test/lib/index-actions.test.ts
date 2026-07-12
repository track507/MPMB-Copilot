import { describe, expect, it } from "vitest";
import { classifyIndexResponse, isIndexBusy } from "@/lib/index-actions";
import type { IndexStatus, IndexTriggerResponse, TaskStatus } from "@/types/settings";

const status = (overrides: Partial<IndexStatus>): IndexStatus => ({
	collection_name: "c",
	total_vectors: 10,
	indexed_files: 2,
	last_updated: null,
	status: "ready",
	task_id: null,
	...overrides,
});

const task = (overrides: Partial<TaskStatus>): TaskStatus => ({
	status: "running",
	progress: 0.5,
	progress_message: null,
	error: null,
	...overrides,
});

describe("classifyIndexResponse", () => {
	it("treats a task id as a started index", () => {
		const resp: IndexTriggerResponse = { status: "in_progress", message: "started", task_id: "t-1" };
		expect(classifyIndexResponse(resp)).toEqual({ kind: "started", taskId: "t-1" });
	});

	it("treats a no-task response as a no-op with the backend message", () => {
		const resp: IndexTriggerResponse = { status: "completed", message: "Index already populated", task_id: null };
		expect(classifyIndexResponse(resp)).toEqual({ kind: "noop", message: "Index already populated" });
	});
});

describe("isIndexBusy", () => {
	it("is busy while the status reports indexing", () => {
		expect(isIndexBusy(status({ status: "indexing" }), undefined)).toBe(true);
	});

	it("is busy while an attached task runs, even if status lags", () => {
		expect(isIndexBusy(status({ status: "ready" }), task({ status: "running" }))).toBe(true);
	});

	it("is idle when the task is terminal and status is ready", () => {
		expect(isIndexBusy(status({ status: "ready" }), task({ status: "completed" }))).toBe(false);
	});
});

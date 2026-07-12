/** Pure decision logic for the reindex controls (kept out of the component for testability) */

import type { IndexStatus, IndexTriggerResponse, TaskStatus } from "@/types/settings";

export type IndexAction = { readonly kind: "started"; readonly taskId: string } | { readonly kind: "noop"; readonly message: string };

export function classifyIndexResponse(resp: IndexTriggerResponse): IndexAction {
	return resp.task_id === null ? { kind: "noop", message: resp.message } : { kind: "started", taskId: resp.task_id };
}

export function isIndexBusy(status: IndexStatus | undefined, task: TaskStatus | undefined): boolean {
	if (task !== undefined && (task.status === "pending" || task.status === "running")) return true;
	return status?.status === "indexing";
}

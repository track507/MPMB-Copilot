import { SettingsPanel } from "@/components/settings/settings-panel";
import type { ReactElement } from "react";

export default function SettingsPage(): ReactElement {
	return (
		<div className="mx-auto max-w-2xl px-4 py-8">
			<h1 className="text-2xl font-bold tracking-tight">Settings</h1>
			<p className="mt-1 text-sm text-muted-foreground">Configure LLM provider, model, and RAG behavior.</p>
			<div className="mt-6">
				<SettingsPanel />
			</div>
		</div>
	);
}

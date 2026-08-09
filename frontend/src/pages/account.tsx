import type { ReactElement } from "react";

// * Capability-driven content (SSO-aware profile, appearance, preferences) is later
export default function AccountPage(): ReactElement {
	return (
		<div className="mx-auto max-w-2xl px-4 py-8">
			<h1 className="text-2xl font-bold tracking-tight">Account</h1>
			<p className="mt-1 text-sm text-muted-foreground">Your personal settings.</p>
			{/* we can add personal settings here later */}
		</div>
	);
}

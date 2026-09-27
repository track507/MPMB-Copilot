import { usePreferencesStore } from "@/stores/preferences-store";
import type { ReactElement } from "react";

// * Section cards (Profile / Appearance / Preferences) fill this as content lands
export default function AccountPage(): ReactElement {
	const showUsage = usePreferencesStore((s) => s.showUsage);
	const setShowUsage = usePreferencesStore((s) => s.setShowUsage);

	return (
		<div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-8">
			<div className="rounded-lg border border-border p-6">
				<h2 className="text-lg font-semibold">Profile</h2>
				<p className="mt-1 text-sm text-muted-foreground">Account details and sign-in methods will appear here.</p>
			</div>

			<div className="rounded-lg border border-border p-6">
				<h2 className="text-lg font-semibold">Display</h2>
				<p className="mt-1 text-sm text-muted-foreground">Stored in this browser, so it applies to you rather than to everyone.</p>

				<label className="mt-4 flex cursor-pointer items-start gap-3">
					<input
						type="checkbox"
						checked={showUsage}
						onChange={(e) => {
							setShowUsage(e.target.checked);
						}}
						className="mt-0.5 size-4 rounded border-input"
					/>
					<span>
						<span className="text-sm font-medium">Show usage and cost</span>
						<span className="block text-xs text-muted-foreground">
							Per-turn cost, the session total, and how full the model&apos;s context is. Costs are estimated from published list prices, not
							billed amounts.
						</span>
					</span>
				</label>
			</div>
		</div>
	);
}

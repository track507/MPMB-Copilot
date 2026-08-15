import type { ReactElement } from "react";

// * Section cards (Profile / Appearance / Preferences) fill this as content lands
export default function AccountPage(): ReactElement {
	return (
		<div className="mx-auto w-full max-w-3xl px-4 py-8">
			<div className="rounded-lg border border-border p-6">
				<h2 className="text-lg font-semibold">Profile</h2>
				<p className="mt-1 text-sm text-muted-foreground">Account details and sign-in methods will appear here.</p>
			</div>
		</div>
	);
}

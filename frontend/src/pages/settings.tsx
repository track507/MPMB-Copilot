import { SettingsPanel } from "@/components/settings/settings-panel";
import type { ReactElement } from "react";

export default function SettingsPage(): ReactElement {
	// * A form reads best in a narrow column, centered inside the wide admin console
	return (
		<div className="mx-auto w-full max-w-2xl">
			<SettingsPanel />
		</div>
	);
}

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface PreferencesState {
	readonly showUsage: boolean;
	readonly setShowUsage: (value: boolean) => void;
}

/**
 * Per-viewer display preferences
 */
export const usePreferencesStore = create<PreferencesState>()(
	persist(
		(set) => ({
			showUsage: true,
			setShowUsage: (value) => {
				set({ showUsage: value });
			},
		}),
		{ name: "mpmb-preferences" }
	)
);

// Temporal API polyfill: installs globalThis.Temporal + ambient types until native support is universal (Safari pending)
// ! This will be dropped when Safari adds full support for Temporal API; see https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Temporal
import "temporal-polyfill/global";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

const rootElement = document.getElementById("root");
if (rootElement === null) {
	throw new Error("Root element not found");
}

createRoot(rootElement).render(
	<StrictMode>
		<App />
	</StrictMode>
);

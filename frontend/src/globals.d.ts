// * Temporal types for the whole frontend, which TypeScript ships in no lib.*.d.ts of its own
// ! temporal-polyfill 1.0 made "temporal-polyfill/global" runtime-only and moved the types to /types/global
// ? Dropping this import leaves every Temporal reference an error type while the runtime still works
import "temporal-polyfill/types/global";

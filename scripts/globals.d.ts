// * Node 24+ ships Temporal natively, but TypeScript has no Temporal types (Stage 3, absent from every lib.*.d.ts)
// * temporal-spec is types-only - no runtime polyfill, unlike the frontend which needs one for browsers
import "temporal-spec/global";

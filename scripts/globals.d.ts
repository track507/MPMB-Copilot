// * TypeScript ships no Temporal types (absent from every lib.*.d.ts); temporal-spec/global supplies them here
// ! Node 24 (the .nvmrc/engines floor) has NO Temporal runtime - only Node 26+ enables it by default - so a
// ! script that uses Temporal at runtime must import "temporal-polyfill/global" itself; this file stays types-only
import "temporal-spec/global";

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// ! globals:false means RTL cannot auto-register its cleanup; without this, components stay mounted across tests
afterEach(cleanup);

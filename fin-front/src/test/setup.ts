import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// With `globals: false`, @testing-library/react's automatic cleanup isn't
// registered, so each render() leaks into the next test's DOM.
afterEach(() => {
  cleanup();
});

import { describe, expect, it } from "vitest";
import { progressValue } from "./utils";

describe("progressValue", () => {
  it("returns the spend/available ratio as a percentage", () => {
    expect(progressValue("4000", "10000")).toBe(40);
  });

  it("clamps to 100 when over budget", () => {
    expect(progressValue("15000", "10000")).toBe(100);
  });

  it("treats null available (unbudgeted) as fully used when there is spend", () => {
    expect(progressValue("850", null)).toBe(100);
  });

  it("treats zero spend with no availability as empty", () => {
    expect(progressValue("0", null)).toBe(0);
    expect(progressValue("0", "0")).toBe(0);
  });

  it("treats a fully-consumed-or-negative available as fully used when overspent", () => {
    expect(progressValue("500", "0")).toBe(100);
    expect(progressValue("500", "-200")).toBe(100);
  });
});

// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BudgetSummaryResponse, ExplainResponse } from "../data/budgetsApi";

vi.mock("@lib/env", () => ({
  isApiConfigured: () => true,
  getApiBaseUrl: () => "",
  getApiDefaultTimeoutMs: () => 1000,
}));

const summaryResponse: BudgetSummaryResponse = {
  year: 2026,
  month: 7,
  period_start: "2026-07-01T00:00:00+00:00",
  period_end: "2026-08-01T00:00:00+00:00",
  categories: [
    {
      category_slug: "groceries",
      is_unbudgeted: false,
      rule_id: "rule-1",
      rule_effective_from: "2026-06-01",
      cap_amount: "10000.0000",
      currency: "INR",
      rollover_mode: "full",
      rollover_in: "6200.0000",
      available: "16200.0000",
      actual_spend: "14000.0000",
      rollover_out: "2200.0000",
      remaining: "2200.0000",
      over_budget: false,
    },
  ],
  unbudgeted: { actual_spend: "0", categories: [] },
};

// Same `current` as the matching entry in summaryResponse.categories — the
// frontend doesn't recompute anything, it just renders what the API sent.
const explainResponse: ExplainResponse = {
  category_slug: "groceries",
  year: 2026,
  month: 7,
  current: summaryResponse.categories[0],
  summary_lines: [
    "Your cap for 'groceries' this month is 10,000.00 INR.",
    "6,200.00 INR rolled over from last month because you had budget left over.",
    "That makes 16,200.00 INR available this month.",
    "You've spent 14,000.00 INR, leaving 2,200.00 INR.",
    "At today's numbers, 2,200.00 INR would roll over into next month.",
  ],
  events: [
    {
      at: "2026-07-15T10:00:00+00:00",
      type: "transaction.update",
      description:
        "A transaction was updated: its amount changed from 9,000.00 INR to 7,500.00 INR; " +
        "its date changed from 20 Jul 2026 to 10 Jun 2026.",
    },
  ],
};

const requestJson = vi.fn(async ({ path }: { path: string }) => {
  if (path.startsWith("/v1/budgets/summary/explain")) return explainResponse;
  if (path.startsWith("/v1/budgets/summary")) return summaryResponse;
  throw new Error(`Unexpected request in test: ${path}`);
});

vi.mock("@lib/http/configureHttpClient", () => ({
  getHttpClient: () => ({ requestJson }),
  configureHttpClient: vi.fn(),
}));

describe("BudgetsApp — explanation panel", () => {
  it("explains rollover source, cap, and recent changes using the API's own numbers and copy", async () => {
    const { BudgetsApp } = await import("./BudgetsApp");
    render(<BudgetsApp />);

    // Initial summary load.
    await screen.findByText("groceries");
    expect(screen.getByText(/14,000\.00/)).toBeTruthy(); // spent
    expect(screen.getByText(/16,200\.00/)).toBeTruthy(); // available

    // Expand the explanation.
    fireEvent.click(screen.getByRole("button", { name: /why is this number what it is/i }));

    // Primary, calm explanation — exactly the strings the API returned.
    for (const line of explainResponse.summary_lines) {
      expect(await screen.findByText(line)).toBeTruthy();
    }

    // Secondary history, clearly separated from the primary explanation.
    expect(screen.getByText("Recent changes")).toBeTruthy();
    expect(
      screen.getByText(/its amount changed from 9,000\.00 INR to 7,500\.00 INR/)
    ).toBeTruthy();

    // Collapsing hides the explanation again.
    fireEvent.click(screen.getByRole("button", { name: /hide explanation/i }));
    expect(screen.queryByText("Recent changes")).toBeNull();
  });

  it("shows a calm 'no changes' message when the history is empty", async () => {
    const noHistory: ExplainResponse = { ...explainResponse, events: [] };
    requestJson.mockImplementation(async ({ path }: { path: string }) => {
      if (path.startsWith("/v1/budgets/summary/explain")) return noHistory;
      if (path.startsWith("/v1/budgets/summary")) return summaryResponse;
      throw new Error(`Unexpected request in test: ${path}`);
    });

    const { BudgetsApp } = await import("./BudgetsApp");
    render(<BudgetsApp />);

    await screen.findByText("groceries");
    fireEvent.click(screen.getByRole("button", { name: /why is this number what it is/i }));

    await screen.findByText(noHistory.summary_lines[0]);
    expect(screen.queryByText("Recent changes")).toBeNull();
  });
});

import type { HttpClient } from "@lib/http/HttpClient";

export type RolloverMode = "none" | "full" | "capped";

export type BudgetRuleRow = {
  id: string;
  user_id: string;
  category_slug: string;
  rule_type: string;
  cap_amount: string;
  currency: string;
  rollover_mode: RolloverMode;
  rollover_cap_amount: string | null;
  effective_from: string; // YYYY-MM-DD, always first-of-month
  created_at: string;
  updated_at: string;
};

export type BudgetRuleUpsertBody = {
  category_slug: string;
  cap_amount: string;
  currency?: string;
  rollover_mode: RolloverMode;
  rollover_cap_amount?: string | null;
  effective_from: string;
};

export type BudgetRulePatchBody = {
  cap_amount?: string;
  currency?: string;
  rollover_mode?: RolloverMode;
  rollover_cap_amount?: string | null;
};

/**
 * A category's computed cap/rollover/spend picture for one period.
 * `is_unbudgeted` is true when no rule covers this period — in that case
 * only `actual_spend` is meaningful and the rest are `null`.
 */
export type CategoryPeriodSummary = {
  category_slug: string;
  is_unbudgeted: boolean;
  rule_id: string | null;
  rule_effective_from: string | null;
  cap_amount: string | null;
  currency: string | null;
  rollover_mode: RolloverMode | null;
  rollover_in: string | null;
  available: string | null;
  actual_spend: string;
  rollover_out: string | null;
  remaining: string | null;
  over_budget: boolean;
};

export type UnbudgetedCategory = {
  category_slug: string;
  actual_spend: string;
};

export type UnbudgetedSummary = {
  actual_spend: string;
  categories: UnbudgetedCategory[];
};

export type BudgetSummaryResponse = {
  year: number;
  month: number;
  period_start: string;
  period_end: string;
  categories: CategoryPeriodSummary[];
  unbudgeted: UnbudgetedSummary;
};

export type ExplainEvent = {
  at: string;
  type: string;
  description: string;
};

export type ExplainResponse = {
  category_slug: string;
  year: number;
  month: number;
  current: CategoryPeriodSummary;
  /** A short, calm narrative of how `current`'s numbers were arrived at
   * (cap, rollover source, what's available, spent/remaining or
   * over-budget). Always derived from `current`. */
  summary_lines: string[];
  /** Plain-language history of recent transaction/rule changes that bear on
   * this category and period, newest first. */
  events: ExplainEvent[];
};

export function createBudgetsApi(http: HttpClient) {
  return {
    /** Computed, rule-adjusted totals for the period — the source of truth
     * for "how much have I spent / how much is left" per category. */
    summary(year: number, month: number): Promise<BudgetSummaryResponse> {
      const q = `?year=${year}&month=${month}`;
      return http.requestJson<BudgetSummaryResponse>({
        path: `/v1/budgets/summary${q}`,
        method: "GET",
      });
    },
    /** Audit-trail explanation of why one category's total is what it is. */
    explain(year: number, month: number, categorySlug: string): Promise<ExplainResponse> {
      const q = `?year=${year}&month=${month}&category_slug=${encodeURIComponent(categorySlug)}`;
      return http.requestJson<ExplainResponse>({
        path: `/v1/budgets/summary/explain${q}`,
        method: "GET",
      });
    },
    listRules(categorySlug?: string): Promise<BudgetRuleRow[]> {
      const q = categorySlug ? `?category_slug=${encodeURIComponent(categorySlug)}` : "";
      return http.requestJson<BudgetRuleRow[]>({ path: `/v1/budget-rules${q}`, method: "GET" });
    },
    /** Create a rule version, or update the existing version for the same
     * (category_slug, effective_from). */
    upsertRule(body: BudgetRuleUpsertBody): Promise<BudgetRuleRow> {
      return http.requestJson<BudgetRuleRow>({
        path: "/v1/budget-rules",
        method: "POST",
        body,
      });
    },
    patchRule(id: string, body: BudgetRulePatchBody): Promise<BudgetRuleRow> {
      return http.requestJson<BudgetRuleRow>({
        path: `/v1/budget-rules/${id}`,
        method: "PATCH",
        body,
      });
    },
    removeRule(id: string): Promise<void> {
      return http.requestJson<void>({ path: `/v1/budget-rules/${id}`, method: "DELETE" });
    },
  };
}

export type BudgetsApi = ReturnType<typeof createBudgetsApi>;

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@lib/api/ApiError";
import { isApiConfigured } from "@lib/env";
import { getHttpClient } from "@lib/http/configureHttpClient";
import { formatInr } from "@lib/money/formatCurrency";
import { createBudgetsApi } from "../data/budgetsApi";
import type {
  BudgetSummaryResponse,
  CategoryPeriodSummary,
  ExplainResponse,
  RolloverMode,
} from "../data/budgetsApi";
import { progressValue } from "../utils";
import { Alert, AlertDescription, AlertTitle } from "@components/ui/alert";
import { Badge } from "@components/ui/badge";
import { Button } from "@components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@components/ui/card";
import { Input } from "@components/ui/input";
import { Label } from "@components/ui/label";
import { Progress } from "@components/ui/progress";
import { Skeleton } from "@components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@components/ui/select";

function currentYm() {
  const d = new Date();
  return { y: d.getFullYear(), m: d.getMonth() + 1 };
}

type FetchStatus = "loading" | "refreshing" | "idle" | "error";

type ExplainState = {
  status: "loading" | "idle" | "error";
  data?: ExplainResponse;
  error?: string;
};

export function BudgetsApp() {
  const hasApi = isApiConfigured();
  const api = useMemo(() => createBudgetsApi(getHttpClient()), []);
  const start = currentYm();
  const [year, setYear] = useState(start.y);
  const [month, setMonth] = useState(start.m);

  const [summary, setSummary] = useState<BudgetSummaryResponse | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const summaryRef = useRef<BudgetSummaryResponse | null>(null);

  // -- rule form (create/upsert, or edit an existing version) -------------
  const [formEditingId, setFormEditingId] = useState<string | null>(null);
  const [formSlug, setFormSlug] = useState("groceries");
  const [formCap, setFormCap] = useState("15000");
  const [formCurrency, setFormCurrency] = useState("INR");
  const [formRollover, setFormRollover] = useState<RolloverMode>("none");
  const [formRolloverCap, setFormRolloverCap] = useState("");
  const [formEffYear, setFormEffYear] = useState(start.y);
  const [formEffMonth, setFormEffMonth] = useState(start.m);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSubmitting, setFormSubmitting] = useState(false);

  // -- "why did this change" explain panel, per category -------------------
  const [expanded, setExpanded] = useState<string | null>(null);
  const [explainState, setExplainState] = useState<Record<string, ExplainState>>({});

  /**
   * Load the summary for the selected period.
   *
   * `keepStale=true` (used after a mutation, same period) keeps the
   * previously-loaded totals on screen while a fresh copy is fetched, but
   * marks the view as "refreshing" so it's clear those numbers may be about
   * to change. `keepStale=false` (used on period change) clears the old
   * totals first, since they belong to a different period than the one now
   * selected — showing them would be misleading, not just stale.
   */
  const load = useCallback(
    async (keepStale: boolean) => {
      if (!hasApi) return;
      const hasStaleData = keepStale && summaryRef.current !== null;
      if (!hasStaleData) setSummary(null);
      setStatus(hasStaleData ? "refreshing" : "loading");
      setError(null);
      try {
        const data = await api.summary(year, month);
        setSummary(data);
        summaryRef.current = data;
        setLastUpdated(new Date());
        setStatus("idle");
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Failed to load budgets");
        setStatus("error");
      }
    },
    [api, hasApi, year, month]
  );

  useEffect(() => {
    setExpanded(null);
    setExplainState({});
    void load(false);
  }, [load]);

  function toggleExplain(slug: string) {
    if (expanded === slug) {
      setExpanded(null);
      return;
    }
    setExpanded(slug);
    if (!explainState[slug]) {
      setExplainState((s) => ({ ...s, [slug]: { status: "loading" } }));
      api
        .explain(year, month, slug)
        .then((data) => setExplainState((s) => ({ ...s, [slug]: { status: "idle", data } })))
        .catch((e) =>
          setExplainState((s) => ({
            ...s,
            [slug]: {
              status: "error",
              error: e instanceof ApiError ? e.message : "Failed to load",
            },
          }))
        );
    }
  }

  function resetForm() {
    setFormEditingId(null);
    setFormSlug("groceries");
    setFormCap("15000");
    setFormCurrency("INR");
    setFormRollover("none");
    setFormRolloverCap("");
    setFormEffYear(year);
    setFormEffMonth(month);
    setFormError(null);
  }

  async function startEdit(cat: CategoryPeriodSummary) {
    if (!cat.rule_id) return;
    setFormError(null);
    setFormEditingId(cat.rule_id);
    setFormSlug(cat.category_slug);
    setFormCap(cat.cap_amount ?? "");
    setFormCurrency(cat.currency ?? "INR");
    setFormRollover((cat.rollover_mode as RolloverMode | null) ?? "none");
    setFormRolloverCap("");
    if (cat.rollover_mode === "capped") {
      try {
        const rules = await api.listRules(cat.category_slug);
        const match = rules.find((r) => r.id === cat.rule_id);
        if (match?.rollover_cap_amount) setFormRolloverCap(match.rollover_cap_amount);
      } catch {
        // Non-fatal: user can re-enter the rollover cap manually.
      }
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setFormSubmitting(true);
    try {
      if (formEditingId) {
        await api.patchRule(formEditingId, {
          cap_amount: formCap,
          currency: formCurrency,
          rollover_mode: formRollover,
          rollover_cap_amount: formRollover === "capped" ? formRolloverCap : null,
        });
      } else {
        await api.upsertRule({
          category_slug: formSlug,
          cap_amount: formCap,
          currency: formCurrency,
          rollover_mode: formRollover,
          rollover_cap_amount: formRollover === "capped" ? formRolloverCap : null,
          effective_from: `${formEffYear}-${String(formEffMonth).padStart(2, "0")}-01`,
        });
      }
      resetForm();
      await load(true);
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setFormSubmitting(false);
    }
  }

  async function onDeleteRule(ruleId: string) {
    setError(null);
    try {
      await api.removeRule(ruleId);
      if (formEditingId === ruleId) resetForm();
      await load(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Delete failed");
    }
  }

  if (!hasApi) {
    return <div className="p-6 text-sm text-muted-foreground">Set VITE_API_BASE_URL.</div>;
  }

  const hasData = summary !== null;
  const isInitialLoad = status === "loading" && !hasData;
  const isRefreshing = status === "refreshing";
  const showErrorBanner = status === "error";

  return (
    <div className="p-4 md:p-8 max-w-3xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Budgets</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Caps, rollovers, and unbudgeted spend — recalculated from your transactions every time
          you load this page.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Period</CardTitle>
          <CardDescription>Year and calendar month (UTC).</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <div className="space-y-2">
            <Label>Year</Label>
            <Input
              type="number"
              className="w-28"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
            />
          </div>
          <div className="space-y-2">
            <Label>Month (1–12)</Label>
            <Input
              type="number"
              min={1}
              max={12}
              className="w-24"
              value={month}
              onChange={(e) => setMonth(Number(e.target.value))}
            />
          </div>
        </CardContent>
      </Card>

      {showErrorBanner ? (
        <Alert variant="destructive">
          <AlertTitle>{hasData ? "Couldn't refresh totals" : "Couldn't load budgets"}</AlertTitle>
          <AlertDescription>
            <p>{error}</p>
            {hasData && lastUpdated ? (
              <p className="mt-1">
                Showing totals as of {lastUpdated.toLocaleTimeString()} — they may be out of date.
              </p>
            ) : null}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2"
              onClick={() => void load(hasData)}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>{formEditingId ? "Edit rule" : "Set / update rule"}</CardTitle>
          <CardDescription>
            {formEditingId
              ? "Editing the rule version active for this period. Category and effective date can't be changed here — delete and recreate to move a rule."
              : "A cap (and optional rollover) for a category, effective from a given month onward."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {formError ? (
            <p className="text-sm text-destructive border rounded-md p-3 mb-4">{formError}</p>
          ) : null}
          <form className="grid gap-4 md:grid-cols-2" onSubmit={onSubmit}>
            <div className="space-y-2">
              <Label>Category slug</Label>
              <Input
                value={formSlug}
                onChange={(e) => setFormSlug(e.target.value)}
                disabled={!!formEditingId}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Cap amount</Label>
              <Input value={formCap} onChange={(e) => setFormCap(e.target.value)} required />
            </div>
            <div className="space-y-2">
              <Label>Currency</Label>
              <Input
                value={formCurrency}
                onChange={(e) => setFormCurrency(e.target.value.toUpperCase())}
                maxLength={3}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Rollover</Label>
              <Select
                value={formRollover}
                onValueChange={(v) => setFormRollover(v as RolloverMode)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None — unused budget doesn't carry over</SelectItem>
                  <SelectItem value="full">Full — all unused budget carries over</SelectItem>
                  <SelectItem value="capped">Capped — carries over up to a limit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {formRollover === "capped" ? (
              <div className="space-y-2">
                <Label>Rollover cap</Label>
                <Input
                  value={formRolloverCap}
                  onChange={(e) => setFormRolloverCap(e.target.value)}
                  required
                />
              </div>
            ) : null}
            {!formEditingId ? (
              <>
                <div className="space-y-2">
                  <Label>Effective from — year</Label>
                  <Input
                    type="number"
                    value={formEffYear}
                    onChange={(e) => setFormEffYear(Number(e.target.value))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Effective from — month</Label>
                  <Input
                    type="number"
                    min={1}
                    max={12}
                    value={formEffMonth}
                    onChange={(e) => setFormEffMonth(Number(e.target.value))}
                  />
                  <p className="text-xs text-muted-foreground">
                    Can be in the past — applies to that month onward, including already-elapsed
                    months.
                  </p>
                </div>
              </>
            ) : null}
            <div className="md:col-span-2 flex gap-2">
              <Button type="submit" disabled={formSubmitting}>
                {formEditingId ? "Save changes" : "Save rule"}
              </Button>
              {formEditingId ? (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancel
                </Button>
              ) : null}
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="text-lg font-medium">This month</h2>
          {isRefreshing ? <Badge variant="outline">Refreshing…</Badge> : null}
          {lastUpdated ? (
            <span className="text-xs text-muted-foreground">
              as of {lastUpdated.toLocaleTimeString()}
            </span>
          ) : null}
        </div>

        {isInitialLoad ? (
          <div className="space-y-2">
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
          </div>
        ) : !hasData ? null : (
          <div className={isRefreshing ? "opacity-60 transition-opacity" : ""}>
            {summary.categories.length === 0 && summary.unbudgeted.categories.length === 0 ? (
              <p className="text-sm text-muted-foreground">No budgets or spend for this month.</p>
            ) : (
              <ul className="space-y-3">
                {summary.categories.map((cat) => {
                  const pct = progressValue(cat.actual_spend, cat.available);
                  const ex = explainState[cat.category_slug];
                  return (
                    <li key={cat.category_slug} className="border rounded-lg p-3 space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{cat.category_slug}</p>
                          {cat.over_budget ? (
                            <Badge variant="destructive">Over budget</Badge>
                          ) : null}
                          {cat.rollover_mode && cat.rollover_mode !== "none" ? (
                            <Badge variant="secondary">{cat.rollover_mode} rollover</Badge>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          <Button type="button" variant="ghost" size="sm" onClick={() => void startEdit(cat)}>
                            Edit
                          </Button>
                          {cat.rule_id ? (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() => void onDeleteRule(cat.rule_id!)}
                            >
                              Delete
                            </Button>
                          ) : null}
                        </div>
                      </div>

                      <Progress value={pct} className={cat.over_budget ? "bg-destructive/20" : ""} />

                      <div className="flex flex-wrap justify-between gap-2 text-sm">
                        <span>
                          <span className="font-semibold tabular-nums">
                            {formatInr(cat.actual_spend, cat.currency ?? "INR")}
                          </span>{" "}
                          spent of{" "}
                          <span className="tabular-nums">
                            {formatInr(cat.available ?? "0", cat.currency ?? "INR")}
                          </span>{" "}
                          available
                        </span>
                        <span className="text-muted-foreground tabular-nums">
                          {Number(cat.remaining ?? "0") >= 0
                            ? `${formatInr(cat.remaining ?? "0", cat.currency ?? "INR")} left`
                            : `${formatInr(
                                String(-Number(cat.remaining ?? "0")),
                                cat.currency ?? "INR"
                              )} over`}
                        </span>
                      </div>

                      <div className="text-xs text-muted-foreground flex flex-wrap gap-x-3">
                        <span>Cap {formatInr(cat.cap_amount ?? "0", cat.currency ?? "INR")}</span>
                        {Number(cat.rollover_in ?? "0") !== 0 ? (
                          <span>
                            Rolled in {formatInr(cat.rollover_in ?? "0", cat.currency ?? "INR")}
                          </span>
                        ) : null}
                        {Number(cat.rollover_out ?? "0") !== 0 ? (
                          <span>
                            Rolling forward{" "}
                            {formatInr(cat.rollover_out ?? "0", cat.currency ?? "INR")}
                          </span>
                        ) : null}
                      </div>

                      <Button
                        type="button"
                        variant="link"
                        size="sm"
                        className="h-auto p-0 text-xs"
                        onClick={() => toggleExplain(cat.category_slug)}
                      >
                        {expanded === cat.category_slug ? "Hide explanation" : "Why is this number what it is?"}
                      </Button>

                      {expanded === cat.category_slug ? (
                        <div className="border-t pt-2 space-y-2">
                          {!ex || ex.status === "loading" ? (
                            <p className="text-xs text-muted-foreground">Loading…</p>
                          ) : ex.status === "error" ? (
                            <p className="text-xs text-destructive">{ex.error}</p>
                          ) : ex.data ? (
                            <>
                              <ul className="text-sm space-y-1">
                                {ex.data.summary_lines.map((line, i) => (
                                  <li key={i}>{line}</li>
                                ))}
                              </ul>
                              {ex.data.events.length > 0 ? (
                                <div className="space-y-1 pt-1">
                                  <p className="text-xs font-medium text-muted-foreground">
                                    Recent changes
                                  </p>
                                  <ul className="text-xs space-y-1">
                                    {ex.data.events.map((event, i) => (
                                      <li key={i} className="text-muted-foreground">
                                        <span className="font-medium text-foreground">
                                          {new Date(event.at).toLocaleString()}:
                                        </span>{" "}
                                        {event.description}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ) : null}
                            </>
                          ) : null}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}

            {summary.unbudgeted.categories.length > 0 ? (
              <div className="border rounded-lg p-3 mt-3 space-y-2 border-dashed">
                <div className="flex items-center justify-between">
                  <p className="font-medium">Unbudgeted spend</p>
                  <span className="font-semibold tabular-nums">
                    {formatInr(summary.unbudgeted.actual_spend, "INR")}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  No active rule covers these categories for this period.
                </p>
                <ul className="text-sm space-y-1">
                  {summary.unbudgeted.categories.map((u) => (
                    <li key={u.category_slug} className="flex justify-between">
                      <span>{u.category_slug}</span>
                      <span className="tabular-nums">{formatInr(u.actual_spend, "INR")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

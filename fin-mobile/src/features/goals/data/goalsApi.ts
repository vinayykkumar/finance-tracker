import type { JsonHttpClient } from "../../../core/http/jsonHttpClient";
import type { FinancialGoalCreate, FinancialGoalRead } from "../domain/goalTypes";

export function createGoalsApi(http: JsonHttpClient) {
  return {
    list(): Promise<FinancialGoalRead[]> {
      return http.requestJson<FinancialGoalRead[]>({ path: "/v1/goals", method: "GET" });
    },
    create(body: FinancialGoalCreate): Promise<FinancialGoalRead> {
      return http.requestJson<FinancialGoalRead>({
        path: "/v1/goals",
        method: "POST",
        body,
      });
    },
    remove(goalId: string): Promise<void> {
      return http.requestJson<void>({
        path: `/v1/goals/${goalId}`,
        method: "DELETE",
      });
    },
  };
}

export type GoalsApi = ReturnType<typeof createGoalsApi>;

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { createJsonHttpClient } from "../../../core/http/jsonHttpClient";
import { getApiBaseUrl } from "../../../core/config";
import { createGoalsApi } from "../data/goalsApi";
import type { FinancialGoalCreate, FinancialGoalRead } from "../domain/goalTypes";

function formatInr(amount: string, currency: string): string {
  const n = Number(amount);
  if (!Number.isFinite(n)) return "—";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency.length === 3 ? currency : "INR",
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `${currency} ${n.toLocaleString("en-IN")}`;
  }
}

export function GoalsScreen() {
  const base = getApiBaseUrl();
  const http = useMemo(
    () => createJsonHttpClient({ getBaseUrl: getApiBaseUrl }),
    []
  );
  const api = useMemo(() => createGoalsApi(http), [http]);

  const [goals, setGoals] = useState<FinancialGoalRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("Wedding fund");
  const [target, setTarget] = useState("500000");
  const [saved, setSaved] = useState("50000");

  const refresh = useCallback(async () => {
    if (!base) return;
    setLoading(true);
    setError(null);
    try {
      setGoals(await api.list());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load goals");
      setGoals([]);
    } finally {
      setLoading(false);
    }
  }, [api, base]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onCreate() {
    if (!base) return;
    setError(null);
    const body: FinancialGoalCreate = {
      name,
      goal_kind: "wedding",
      currency: "INR",
      target_amount: target,
      saved_amount: saved,
    };
    try {
      await api.create(body);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Create failed");
    }
  }

  async function onDelete(id: string) {
    if (!base) return;
    try {
      await api.remove(id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (!base) {
    return (
      <View style={styles.pad}>
        <Text style={styles.title}>Goals</Text>
        <Text style={styles.muted}>
          Set EXPO_PUBLIC_API_BASE_URL (e.g. http://10.0.2.2:8000 on Android emulator) and run the
          backend with app.main_auth. Log in via the web app once so the session cookie is issued
          (same API host), or add a mobile login flow later.
        </Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.pad}>
      <Text style={styles.title}>Goals & events</Text>
      {error ? <Text style={styles.err}>{error}</Text> : null}

      <Text style={styles.section}>New goal (INR)</Text>
      <TextInput style={styles.input} value={name} onChangeText={setName} placeholder="Name" />
      <TextInput
        style={styles.input}
        value={target}
        onChangeText={setTarget}
        placeholder="Target amount"
        keyboardType="decimal-pad"
      />
      <TextInput
        style={styles.input}
        value={saved}
        onChangeText={setSaved}
        placeholder="Already saved"
        keyboardType="decimal-pad"
      />
      <Pressable style={styles.btn} onPress={() => void onCreate()}>
        <Text style={styles.btnText}>Create</Text>
      </Pressable>

      <Text style={[styles.section, { marginTop: 24 }]}>Your goals</Text>
      {loading && goals.length === 0 ? (
        <ActivityIndicator />
      ) : (
        goals.map((g) => (
          <View key={g.id} style={styles.card}>
            <Text style={styles.cardTitle}>{g.name}</Text>
            <Text style={styles.muted}>
              Target {formatInr(g.target_amount, g.currency)} · Saved{" "}
              {formatInr(g.saved_amount, g.currency)}
            </Text>
            {g.suggested_monthly_contribution != null ? (
              <Text style={styles.highlight}>
                Suggested / month: {formatInr(g.suggested_monthly_contribution, g.currency)}
              </Text>
            ) : null}
            <Pressable style={styles.btnOutline} onPress={() => void onDelete(g.id)}>
              <Text style={styles.btnOutlineText}>Delete</Text>
            </Pressable>
          </View>
        ))
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: "#fff" },
  pad: { padding: 16, paddingBottom: 48 },
  title: { fontSize: 22, fontWeight: "600", marginBottom: 8 },
  section: { fontSize: 16, fontWeight: "500", marginBottom: 8 },
  muted: { color: "#64748b", fontSize: 13, marginBottom: 8 },
  err: { color: "#b91c1c", marginBottom: 12, fontSize: 13 },
  input: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
    fontSize: 16,
  },
  btn: {
    backgroundColor: "#0f172a",
    padding: 14,
    borderRadius: 8,
    alignItems: "center",
  },
  btnText: { color: "#fff", fontWeight: "600" },
  card: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 12,
    padding: 12,
    marginBottom: 12,
  },
  cardTitle: { fontSize: 16, fontWeight: "600", marginBottom: 4 },
  highlight: { color: "#0f172a", fontWeight: "500", marginTop: 6 },
  btnOutline: {
    marginTop: 10,
    borderWidth: 1,
    borderColor: "#cbd5e1",
    padding: 10,
    borderRadius: 8,
    alignItems: "center",
  },
  btnOutlineText: { color: "#334155", fontWeight: "500" },
});

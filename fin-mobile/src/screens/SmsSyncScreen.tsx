import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";

import { createSmsApi } from "../api/smsApi";
import { getExtraHeadersForApi } from "../core/http/csrfStore";
import { createJsonHttpClient } from "../core/http/jsonHttpClient";
import { getApiBaseUrl, getDefaultTimeoutMs, isApiConfigured } from "../core/config";
import { ApiError } from "../core/api/ApiError";
import { getSmsPermissionStatus, requestSmsPermission } from "../features/smsSync/permissions";
import { getLastSyncedAtMs, getSmsSyncEnabled, setLastSyncedAtMs, setSmsSyncEnabled } from "../features/smsSync/storage";
import { scanDeviceSms, syncCandidates } from "../features/smsSync/syncService";
import type { SmsPermissionStatus, SmsSyncOutcome } from "../features/smsSync/types";

export function SmsSyncScreen() {
  const http = useMemo(
    () =>
      createJsonHttpClient({
        getBaseUrl: getApiBaseUrl,
        defaultTimeoutMs: getDefaultTimeoutMs(),
        getExtraHeaders: getExtraHeadersForApi,
      }),
    []
  );
  const api = useMemo(() => createSmsApi(http), [http]);

  const [hydrated, setHydrated] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [permission, setPermission] = useState<SmsPermissionStatus>("unavailable");
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [lastOutcome, setLastOutcome] = useState<SmsSyncOutcome | null>(null);

  const refresh = useCallback(async () => {
    const [isEnabled, perm, lastSync] = await Promise.all([
      getSmsSyncEnabled(),
      getSmsPermissionStatus(),
      getLastSyncedAtMs(),
    ]);
    setEnabled(isEnabled);
    setPermission(perm);
    setLastSyncedAt(lastSync);
  }, []);

  useEffect(() => {
    void (async () => {
      await refresh();
      setHydrated(true);
    })();
  }, [refresh]);

  async function onToggle(next: boolean) {
    setError(null);
    setInfo(null);

    if (!next) {
      await setSmsSyncEnabled(false);
      setEnabled(false);
      setLastSyncedAt(null);
      return;
    }

    if (Platform.OS !== "android") {
      setError("SMS sync reads your device's SMS inbox and is only available on Android.");
      return;
    }

    const status = await requestSmsPermission();
    setPermission(status);
    if (status !== "granted") {
      setError(
        "Permission denied — SMS sync stays off. You can allow \"SMS\" access later from your " +
          "phone's Settings → Apps → this app → Permissions."
      );
      return;
    }

    await setSmsSyncEnabled(true);
    setEnabled(true);
  }

  async function onSyncNow() {
    setError(null);
    setInfo(null);
    setBusy(true);
    try {
      // Re-check: the user may have revoked the permission from system
      // Settings since this screen last loaded.
      const currentPermission = await getSmsPermissionStatus();
      setPermission(currentPermission);
      if (currentPermission !== "granted") {
        setEnabled(false);
        await setSmsSyncEnabled(false);
        setError("SMS permission was revoked, so sync was turned off. Re-enable it above to sync again.");
        return;
      }

      const sinceMs = (await getLastSyncedAtMs()) ?? undefined;
      const scan = await scanDeviceSms(sinceMs ? { sinceMs } : undefined);

      if (scan.candidates.length === 0) {
        setInfo(
          `Scanned ${scan.scanned} recent message(s); none looked like bank/UPI alerts ` +
            `(${scan.excluded} excluded). Nothing to sync.`
        );
        return;
      }

      const confirmed = await confirmSync(scan.candidates.length, scan.scanned, scan.excluded);
      if (!confirmed) {
        setInfo("Sync cancelled — nothing was sent.");
        return;
      }

      const outcome = await syncCandidates(api, scan.candidates);
      setLastOutcome(outcome);
      const now = Date.now();
      setLastSyncedAt(now);
      await setLastSyncedAtMs(now);
      setInfo(
        `Synced ${outcome.synced} message(s): ${outcome.created} new, ${outcome.duplicates} already had, ` +
          `${outcome.parsed} recognized, ${outcome.unparsed} unrecognized, ${outcome.rejected} rejected.`
      );
    } catch (e) {
      const partial = (e as { partialOutcome?: SmsSyncOutcome }).partialOutcome;
      if (partial && partial.synced > 0) {
        setLastOutcome(partial);
        setError(
          `Sync interrupted after ${partial.synced} of ${partial.candidates} message(s) — ` +
            `the rest can be retried with "Sync now".${describeError(e)}`
        );
      } else {
        setError(describeError(e));
      }
      // Refresh permission state in case the failure was a mid-sync revoke.
      setPermission(await getSmsPermissionStatus());
    } finally {
      setBusy(false);
    }
  }

  if (!hydrated) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.pad}>
      <Text style={styles.title}>SMS bank alerts</Text>
      <Text style={styles.body}>
        When enabled, this app reads recent SMS from senders that look like banks or UPI apps and
        sends only those messages to your account so transaction alerts can be reviewed here later.
      </Text>
      <View style={styles.card}>
        <Text style={styles.subTitle}>What never leaves your device</Text>
        <Text style={styles.body}>
          • Messages containing OTPs, PINs, CVVs, or passwords{"\n"}
          • Messages from senders that don't look like banks (personal contacts, etc.){"\n"}
          • Anything, the moment you turn this off
        </Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.subTitle}>What is sent, if enabled</Text>
        <Text style={styles.body}>
          The sender, full text, and timestamp of messages that look like bank/UPI transaction
          alerts — sent over your existing signed-in session to build a list of detected
          transactions. See PRIVACY-SMS.md in the repo for the full data-handling note.
        </Text>
      </View>

      {!isApiConfigured() ? <Text style={styles.err}>Set EXPO_PUBLIC_API_BASE_URL.</Text> : null}

      <View style={[styles.card, styles.row]}>
        <View style={styles.flexShrink}>
          <Text style={styles.subTitle}>Enable SMS sync</Text>
          <Text style={styles.muted}>
            {Platform.OS !== "android"
              ? "Android only"
              : permission === "granted"
                ? "Permission granted"
                : "Requires SMS permission"}
          </Text>
        </View>
        <Switch value={enabled} onValueChange={(v) => void onToggle(v)} disabled={busy} />
      </View>

      {error ? <Text style={styles.err}>{error}</Text> : null}
      {info ? <Text style={styles.info}>{info}</Text> : null}

      {permission === "denied" && Platform.OS === "android" ? (
        <Pressable style={styles.btnOutline} onPress={() => void Linking.openSettings()}>
          <Text style={styles.btnOutlineText}>Open app settings</Text>
        </Pressable>
      ) : null}

      <Pressable
        style={[styles.btn, (!enabled || busy) && styles.btnDisabled]}
        onPress={() => void onSyncNow()}
        disabled={!enabled || busy}
      >
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Sync now</Text>}
      </Pressable>

      <Text style={styles.muted}>
        {lastSyncedAt ? `Last synced ${new Date(lastSyncedAt).toLocaleString()}` : "Never synced"}
      </Text>

      {lastOutcome ? (
        <View style={styles.card}>
          <Text style={styles.subTitle}>Last sync result</Text>
          <Text style={styles.body}>
            {lastOutcome.synced} sent · {lastOutcome.created} new · {lastOutcome.duplicates} duplicate ·{" "}
            {lastOutcome.parsed} recognized · {lastOutcome.unparsed} unrecognized ·{" "}
            {lastOutcome.rejected} rejected
          </Text>
        </View>
      ) : null}
    </ScrollView>
  );
}

function confirmSync(candidateCount: number, scanned: number, excluded: number): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(
      "Sync SMS alerts?",
      `${candidateCount} of ${scanned} recent message(s) look like bank/UPI alerts ` +
        `(${excluded} excluded as personal or sensitive). Send these ${candidateCount} to your account?`,
      [
        { text: "Cancel", style: "cancel", onPress: () => resolve(false) },
        { text: "Sync", onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) }
    );
  });
}

/** Never includes message bodies — only short, user-facing status text. */
function describeError(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Sync failed.";
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: "#fff" },
  center: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#fff" },
  pad: { padding: 16, paddingBottom: 48 },
  title: { fontSize: 22, fontWeight: "600", marginBottom: 8 },
  subTitle: { fontSize: 14, fontWeight: "600", marginBottom: 4, color: "#0f172a" },
  body: { fontSize: 13, color: "#334155", lineHeight: 19 },
  muted: { color: "#64748b", fontSize: 12, marginTop: 8 },
  err: { color: "#b91c1c", marginBottom: 8, fontSize: 13 },
  info: { color: "#15803d", marginBottom: 8, fontSize: 13 },
  card: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
  },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  flexShrink: { flexShrink: 1, marginRight: 12 },
  btn: {
    backgroundColor: "#0f172a",
    padding: 14,
    borderRadius: 8,
    alignItems: "center",
    marginBottom: 12,
  },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: "#fff", fontWeight: "600" },
  btnOutline: {
    borderWidth: 1,
    borderColor: "#cbd5e1",
    padding: 12,
    borderRadius: 8,
    alignItems: "center",
    marginBottom: 12,
  },
  btnOutlineText: { color: "#334155", fontWeight: "500" },
});

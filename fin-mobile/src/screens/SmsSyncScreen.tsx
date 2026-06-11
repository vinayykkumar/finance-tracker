/**
 * SmsSyncScreen — full-page view for the Bank SMS Sync feature.
 *
 * Consent-first design
 * ---------------------
 * The user sees a plain-language description of what will be read, what
 * leaves the device, and what never does — BEFORE the system permission
 * dialog is shown and BEFORE any data is uploaded.
 *
 * Permission revocation
 * ---------------------
 * If the user has already synced and later revokes READ_SMS in system
 * settings, the next sync attempt will surface an error with a link to
 * open Settings.  In-progress syncs cannot be interrupted mid-flight on
 * Android (permission revocation only takes effect after the app restarts).
 */

import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSmsSync } from "../sms/useSmsSync";

export function SmsSyncScreen() {
  const { status, result, startSync, reset } = useSmsSync();

  const isRunning = status === "requesting_permission" || status === "reading" || status === "uploading";

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.pad}>
      <Text style={styles.title}>Bank SMS Sync</Text>

      {/* ── What this does ─────────────────────────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>What Fin reads</Text>
        <Text style={styles.body}>
          Fin scans your SMS inbox for bank transaction alerts (debits and
          credits) from the last 30 days.
        </Text>
        <Text style={[styles.body, styles.mt8]}>
          <Text style={styles.bold}>What stays on your device: </Text>
          all personal SMS, OTPs, and non-financial messages — these are
          filtered locally and never sent.
        </Text>
        <Text style={[styles.body, styles.mt8]}>
          <Text style={styles.bold}>What is uploaded: </Text>
          sender ID, a cryptographic hash of the message text (not the text
          itself), the detected amount and type, and the message timestamp.
        </Text>
        {Platform.OS !== "android" && (
          <Text style={[styles.body, styles.mt8, styles.muted]}>
            SMS sync is only available on Android.
          </Text>
        )}
      </View>

      {/* ── Status / result card ───────────────────────────────────── */}
      {status === "idle" && !result && (
        <Pressable
          style={[styles.btn, Platform.OS !== "android" && styles.btnDisabled]}
          onPress={() => void startSync()}
          disabled={Platform.OS !== "android"}
          accessibilityRole="button"
          accessibilityLabel="Start bank SMS sync"
        >
          <Text style={styles.btnText}>
            {Platform.OS === "android" ? "Sync Bank SMS" : "Android only"}
          </Text>
        </Pressable>
      )}

      {isRunning && (
        <View style={styles.statusCard}>
          <ActivityIndicator size="small" color="#0f172a" />
          <Text style={styles.statusText}>{labelForStatus(status)}</Text>
        </View>
      )}

      {status === "done" && result && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Sync complete</Text>
          <ResultRow label="Messages scanned" value={result.scanned} />
          <ResultRow label="Financial alerts found" value={result.filtered} />
          <ResultRow label="New records stored" value={result.accepted} />
          <ResultRow label="Already synced (skipped)" value={result.duplicates} />
          {result.rejected > 0 && (
            <ResultRow label="Rejected (validation)" value={result.rejected} />
          )}
          <Pressable style={[styles.btn, styles.btnSecondary, styles.mt16]} onPress={reset}>
            <Text style={styles.btnSecondaryText}>Sync again</Text>
          </Pressable>
        </View>
      )}

      {status === "error" && result && (
        <View style={[styles.card, styles.errorCard]}>
          <Text style={styles.cardTitle}>Sync failed</Text>
          <Text style={styles.errorText}>{result.errorMessage}</Text>
          {result.errorMessage?.includes("permanently denied") && (
            <Pressable
              style={styles.linkBtn}
              onPress={() => void Linking.openSettings()}
              accessibilityRole="link"
            >
              <Text style={styles.linkText}>Open App Settings</Text>
            </Pressable>
          )}
          <Pressable style={[styles.btn, styles.btnSecondary, styles.mt16]} onPress={reset}>
            <Text style={styles.btnSecondaryText}>Try again</Text>
          </Pressable>
        </View>
      )}

      {/* ── Privacy note ───────────────────────────────────────────── */}
      <Text style={styles.privacyNote}>
        You can disable SMS sync at any time by going to Settings → Apps → Fin
        → Permissions and revoking SMS access.  Already-synced data can be
        deleted from your account on request.
      </Text>
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ResultRow({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      <Text style={styles.rowValue}>{value}</Text>
    </View>
  );
}

function labelForStatus(status: string): string {
  if (status === "requesting_permission") return "Requesting permission…";
  if (status === "reading") return "Reading SMS inbox…";
  if (status === "uploading") return "Uploading to server…";
  return "";
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: "#fff" },
  pad: { padding: 16, paddingBottom: 48 },
  title: { fontSize: 22, fontWeight: "600", marginBottom: 16, color: "#0f172a" },

  card: {
    borderWidth: 1,
    borderColor: "#e2e8f0",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  errorCard: { borderColor: "#fca5a5", backgroundColor: "#fff1f2" },
  cardTitle: { fontSize: 15, fontWeight: "600", color: "#0f172a", marginBottom: 8 },

  body: { fontSize: 14, color: "#334155", lineHeight: 20 },
  bold: { fontWeight: "600" },
  muted: { color: "#94a3b8" },
  mt8: { marginTop: 8 },
  mt16: { marginTop: 16 },

  btn: {
    backgroundColor: "#0f172a",
    padding: 14,
    borderRadius: 8,
    alignItems: "center",
    marginBottom: 16,
  },
  btnDisabled: { backgroundColor: "#94a3b8" },
  btnText: { color: "#fff", fontWeight: "600", fontSize: 15 },

  btnSecondary: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: "#cbd5e1",
  },
  btnSecondaryText: { color: "#334155", fontWeight: "600" },

  statusCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    padding: 14,
    marginBottom: 16,
  },
  statusText: { color: "#334155", fontSize: 14 },

  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 5,
    borderBottomWidth: 1,
    borderBottomColor: "#f1f5f9",
  },
  rowLabel: { fontSize: 14, color: "#475569" },
  rowValue: { fontSize: 14, fontWeight: "600", color: "#0f172a" },

  errorText: { fontSize: 14, color: "#b91c1c", lineHeight: 20 },
  linkBtn: { marginTop: 8 },
  linkText: { color: "#0f172a", textDecorationLine: "underline", fontSize: 14 },

  privacyNote: {
    fontSize: 12,
    color: "#94a3b8",
    lineHeight: 18,
    marginTop: 8,
  },
});

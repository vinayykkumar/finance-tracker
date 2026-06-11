/**
 * Hook that orchestrates the full SMS sync flow:
 *
 *   1. Check / request READ_SMS permission.
 *   2. Read recent messages from device inbox (bounded window).
 *   3. Apply client-side prefilter (OTP, non-financial).
 *   4. Chunk and upload filtered messages to the backend.
 *   5. Return final counts so the UI can render feedback.
 *
 * Privacy guarantees honoured here
 * ----------------------------------
 * - No message body is logged to console or analytics at any point.
 * - The prefilter runs entirely on-device before any network call.
 * - `body` is sent to the backend but stored only as a SHA-256 hash there.
 *
 * Permission revocation mid-sync
 * --------------------------------
 * Android cannot revoke a permission while the app is in the foreground — the
 * user must go to Settings and force-stop the app.  On the next launch,
 * `checkSmsReadPermission()` will return false and sync will not start.
 * We still guard every phase defensively and surface errors.
 */

import { useCallback, useState } from "react";

import { ApiError } from "../core/api/ApiError";
import { createJsonHttpClient } from "../core/http/jsonHttpClient";
import { getApiBaseUrl, getDefaultTimeoutMs } from "../core/config";
import { getExtraHeadersForApi } from "../core/http/csrfStore";
import { checkSmsReadPermission, requestSmsReadPermission } from "./permissions";
import { prefilterMessages } from "./prefilter";
import { readRecentSms } from "./reader";
import { createSmsIngestApi, type SmsItemIn } from "./smsIngestApi";

const BATCH_SIZE = 50; // items per HTTP request — well under the server's limit of 100
const MAX_AGE_DAYS = 30;
const MAX_MESSAGES = 200;

export type SyncStatus =
  | "idle"
  | "requesting_permission"
  | "reading"
  | "uploading"
  | "done"
  | "error";

export type SyncResult = {
  scanned: number;
  filtered: number;
  accepted: number;
  duplicates: number;
  rejected: number;
  errorMessage?: string;
};

export type UseSmsSync = {
  status: SyncStatus;
  result: SyncResult | null;
  /** Call this to kick off the permission → read → upload flow. */
  startSync: () => Promise<void>;
  /** Reset back to idle so the user can try again. */
  reset: () => void;
};

const emptyResult = (): SyncResult => ({
  scanned: 0,
  filtered: 0,
  accepted: 0,
  duplicates: 0,
  rejected: 0,
});

function toIso(d: Date): string {
  return d.toISOString();
}

function chunkArray<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) {
    chunks.push(arr.slice(i, i + size));
  }
  return chunks;
}

export function useSmsSync(): UseSmsSync {
  const [status, setStatus] = useState<SyncStatus>("idle");
  const [result, setResult] = useState<SyncResult | null>(null);

  const reset = useCallback(() => {
    setStatus("idle");
    setResult(null);
  }, []);

  const startSync = useCallback(async () => {
    if (status !== "idle") return;
    setStatus("requesting_permission");
    setResult(null);

    // ── 1. Permission ─────────────────────────────────────────────────────
    const alreadyGranted = await checkSmsReadPermission();
    if (!alreadyGranted) {
      const outcome = await requestSmsReadPermission();
      if (outcome !== "granted") {
        setResult({
          ...emptyResult(),
          errorMessage:
            outcome === "blocked"
              ? "SMS permission is permanently denied. Go to App Settings → Permissions to re-enable."
              : "SMS permission was not granted.",
        });
        setStatus("error");
        return;
      }
    }

    // ── 2. Read ───────────────────────────────────────────────────────────
    setStatus("reading");
    let raw;
    try {
      raw = await readRecentSms({ maxAgeDays: MAX_AGE_DAYS, maxCount: MAX_MESSAGES });
    } catch (e) {
      setResult({
        ...emptyResult(),
        errorMessage: `Failed to read SMS: ${e instanceof Error ? e.message : String(e)}`,
      });
      setStatus("error");
      return;
    }

    // ── 3. Prefilter ──────────────────────────────────────────────────────
    const filtered = prefilterMessages(raw);

    // ── 4. Upload ─────────────────────────────────────────────────────────
    setStatus("uploading");

    const http = createJsonHttpClient({
      getBaseUrl: getApiBaseUrl,
      defaultTimeoutMs: getDefaultTimeoutMs(),
      getExtraHeaders: getExtraHeadersForApi,
    });
    const api = createSmsIngestApi(http);

    const items: SmsItemIn[] = filtered.map((m) => ({
      device_message_id: m.id,
      sender: m.sender,
      body: m.body,
      received_at: toIso(m.receivedAt),
    }));

    const acc = emptyResult();
    acc.scanned = raw.length;
    acc.filtered = filtered.length;

    const chunks = chunkArray(items, BATCH_SIZE);
    for (const chunk of chunks) {
      try {
        const batchResult = await api.ingestBatch(chunk);
        acc.accepted += batchResult.accepted;
        acc.duplicates += batchResult.duplicates;
        acc.rejected += batchResult.rejected.length;
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : String(e);
        acc.errorMessage = `Upload error: ${msg}`;
        setResult(acc);
        setStatus("error");
        return;
      }
    }

    setResult(acc);
    setStatus("done");
  }, [status]);

  return { status, result, startSync, reset };
}

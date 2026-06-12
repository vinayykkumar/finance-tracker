import type { SmsApi, SmsSyncResponse } from "../../api/smsApi";
import { shouldIncludeSms } from "./prefilter";
import { readInboxSms } from "./smsReader";
import type { ScanResult, SmsCandidate, SmsSyncOutcome } from "./types";

/** How far back to look on a normal sync. */
export const DEFAULT_WINDOW_DAYS = 30;
/** Hard cap on how many raw inbox messages we ever read in one pass. */
export const DEFAULT_MAX_SCAN = 200;
/** Matches the backend's MAX_BATCH_SIZE (app/modules/sms_messages/schemas.py). */
export const SYNC_BATCH_SIZE = 25;

/**
 * Read recent device SMS and apply the on-device prefilter.
 *
 * Nothing is sent to the network here — this is the "preview" step so the
 * UI can show the user what *would* be synced before any bank SMS leaves
 * the device.
 */
export async function scanDeviceSms(opts?: {
  windowDays?: number;
  maxScan?: number;
  sinceMs?: number;
  nowMs?: number;
}): Promise<ScanResult> {
  const windowDays = opts?.windowDays ?? DEFAULT_WINDOW_DAYS;
  const nowMs = opts?.nowMs ?? Date.now();
  const sinceMs = opts?.sinceMs ?? nowMs - windowDays * 24 * 60 * 60 * 1000;
  const maxScan = opts?.maxScan ?? DEFAULT_MAX_SCAN;

  const messages = await readInboxSms({ sinceMs, maxCount: maxScan });

  const candidates: SmsCandidate[] = [];
  let excluded = 0;
  for (const m of messages) {
    if (!shouldIncludeSms(m)) {
      excluded += 1;
      continue;
    }
    candidates.push({
      deviceMsgId: m.id,
      sender: m.address,
      body: m.body,
      receivedAtMs: m.date,
    });
  }

  return { scanned: messages.length, candidates, excluded };
}

function emptyOutcome(candidateCount: number): SmsSyncOutcome {
  return {
    candidates: candidateCount,
    synced: 0,
    created: 0,
    duplicates: 0,
    parsed: 0,
    unparsed: 0,
    rejected: 0,
  };
}

function addResponse(outcome: SmsSyncOutcome, resp: SmsSyncResponse): void {
  outcome.synced += resp.received;
  outcome.created += resp.created;
  outcome.duplicates += resp.duplicates;
  outcome.parsed += resp.parsed;
  outcome.unparsed += resp.unparsed;
  outcome.rejected += resp.rejected;
}

/**
 * Send prefiltered candidates to the API in bounded batches.
 *
 * Batches are sent sequentially and independently: if one batch fails (e.g.
 * the network drops mid-sync), everything synced so far is already
 * durable server-side (each item is idempotent by fingerprint), and the
 * thrown error carries the partial `outcome` so the UI can report
 * "synced N of M" rather than an all-or-nothing failure.
 */
export async function syncCandidates(api: SmsApi, candidates: SmsCandidate[]): Promise<SmsSyncOutcome> {
  const outcome = emptyOutcome(candidates.length);

  for (let i = 0; i < candidates.length; i += SYNC_BATCH_SIZE) {
    const batch = candidates.slice(i, i + SYNC_BATCH_SIZE);
    let resp: SmsSyncResponse;
    try {
      resp = await api.sync(
        batch.map((c) => ({
          sender: c.sender,
          body: c.body,
          received_at: new Date(c.receivedAtMs).toISOString(),
          device_msg_id: c.deviceMsgId,
        }))
      );
    } catch (e) {
      (e as { partialOutcome?: SmsSyncOutcome }).partialOutcome = outcome;
      throw e;
    }
    addResponse(outcome, resp);
  }

  return outcome;
}

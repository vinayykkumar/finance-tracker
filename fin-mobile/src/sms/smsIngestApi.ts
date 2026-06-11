/**
 * API client for POST /v1/sms-ingest/batch.
 *
 * Mirrors the backend ``BatchIn`` / ``BatchResult`` schemas.
 * The HTTP client is the same shared ``JsonHttpClient`` used everywhere else
 * in the app — cookie session and CSRF token are carried automatically.
 */

import type { JsonHttpClient } from "../core/http/jsonHttpClient";

// ---------------------------------------------------------------------------
// Request / response types (must stay in sync with backend schemas.py)
// ---------------------------------------------------------------------------

export type SmsItemIn = {
  device_message_id: string;
  sender: string;
  /** Full message body — body is hashed server-side, never stored in full. */
  body: string;
  /** ISO-8601 timestamp with timezone. */
  received_at: string;
};

export type RejectedItem = {
  device_message_id: string;
  reason: string;
};

export type BatchResult = {
  accepted: number;
  duplicates: number;
  rejected: RejectedItem[];
};

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

export function createSmsIngestApi(http: JsonHttpClient) {
  return {
    /**
     * Upload a batch of SMS items.
     *
     * The server deduplicates by fingerprint so retrying the same batch is safe.
     * Maximum 100 items per call — callers must chunk larger sets.
     */
    ingestBatch(items: SmsItemIn[]): Promise<BatchResult> {
      return http.requestJson<BatchResult>({
        path: "/v1/sms-ingest/batch",
        method: "POST",
        body: { items },
      });
    },
  };
}

export type SmsIngestApi = ReturnType<typeof createSmsIngestApi>;

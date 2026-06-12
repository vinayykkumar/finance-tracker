import type { JsonHttpClient } from "../core/http/jsonHttpClient";

export type SmsParseStatus = "parsed" | "unparsed" | "rejected";

export type SmsMessageIngest = {
  sender: string;
  body: string;
  /** ISO 8601 — the device's clock, which may be skewed from the server's. */
  received_at: string;
  device_msg_id?: string | null;
};

export type SmsSyncResultItem = {
  id: string;
  device_msg_id: string | null;
  fingerprint: string;
  duplicate: boolean;
  parse_status: SmsParseStatus;
  parser_template: string | null;
  reject_reason: string | null;
};

export type SmsSyncResponse = {
  results: SmsSyncResultItem[];
  received: number;
  created: number;
  duplicates: number;
  parsed: number;
  unparsed: number;
  rejected: number;
};

export type SmsMessageRow = {
  id: string;
  source: string;
  sender: string;
  sender_key: string;
  device_msg_id: string | null;
  received_at: string;
  body: string;
  body_length: number;
  parse_status: SmsParseStatus;
  parser_template: string | null;
  parsed_payload: Record<string, string> | null;
  reject_reason: string | null;
  created_at: string;
};

export function createSmsApi(http: JsonHttpClient) {
  return {
    /** POST a batch (max 50) of device SMS for idempotent ingest. */
    sync(messages: SmsMessageIngest[]): Promise<SmsSyncResponse> {
      return http.requestJson<SmsSyncResponse>({
        path: "/v1/sms-messages/sync",
        method: "POST",
        body: { messages },
      });
    },
    list(params?: { parseStatus?: SmsParseStatus; limit?: number }): Promise<SmsMessageRow[]> {
      const q = new URLSearchParams();
      if (params?.parseStatus) q.set("parse_status", params.parseStatus);
      if (params?.limit) q.set("limit", String(params.limit));
      const qs = q.toString();
      return http.requestJson<SmsMessageRow[]>({
        path: `/v1/sms-messages${qs ? `?${qs}` : ""}`,
        method: "GET",
      });
    },
  };
}

export type SmsApi = ReturnType<typeof createSmsApi>;

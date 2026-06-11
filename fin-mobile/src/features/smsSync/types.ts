/** One row as read from the device's SMS inbox (Android `content://sms/inbox`). */
export type DeviceSmsMessage = {
  /** Device-local SMS provider `_id` — stable across reads on the same device install. */
  id: string;
  /** Sender address: a DLT header (e.g. "AD-HDFCBK") or phone number. */
  address: string;
  body: string;
  /** Epoch milliseconds, device clock. */
  date: number;
};

/** A device message that survived the on-device prefilter and is queued to sync. */
export type SmsCandidate = {
  deviceMsgId: string;
  sender: string;
  body: string;
  receivedAtMs: number;
};

/** Result of scanning the device inbox, before anything is sent to the API. */
export type ScanResult = {
  scanned: number;
  candidates: SmsCandidate[];
  /** Messages excluded by the prefilter (non-bank-looking OR sensitive, e.g. OTP). */
  excluded: number;
};

/** Aggregate result of syncing one or more candidates to the API. */
export type SmsSyncOutcome = {
  candidates: number;
  synced: number;
  created: number;
  duplicates: number;
  parsed: number;
  unparsed: number;
  rejected: number;
};

export type SmsPermissionStatus = "granted" | "denied" | "unavailable";

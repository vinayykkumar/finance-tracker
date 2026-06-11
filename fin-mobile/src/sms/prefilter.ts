/**
 * Client-side prefilter — decides which messages are worth uploading.
 *
 * Purpose
 * -------
 * Reduce noise and avoid sending obviously personal or OTP messages to the
 * backend, even though the backend never stores raw bodies.  This is a
 * best-effort privacy layer, not a security boundary.
 *
 * Heuristic rationale
 * -------------------
 * 1. OTP / auth codes — six-digit codes, "one time password", "passcode".
 *    These are explicitly excluded.  They contain no financial data.
 * 2. Financial keywords — at least one of: debited, credited, payment,
 *    transaction, transfer, INR, Rs., balance.  If none are present the
 *    message is not relevant to us.
 * 3. Short bodies — anything under 20 chars can't carry useful structure.
 *
 * False-negative tolerance: a financial message that slips through the OTP
 * filter is fine — the backend will store it as "unparsed".
 * False-positive tolerance: a non-financial message that passes is not
 * catastrophic — body is hashed, not stored; parsed_payload will be null.
 */

const OTP_RE =
  /\b(?:OTP|one.?time.?(?:password|pass(?:code)?|code)|passcode|verification\s+code)\b/i;

const FINANCIAL_RE =
  /\b(?:debited|credited|debit|credit|payment|transaction|transfer|INR|Rs\.?|balance)\b/i;

const MIN_BODY_LENGTH = 20;

export type RawMessage = {
  /** Android SMS content-provider _id (opaque, unique per device) */
  id: string;
  /** Raw sender address e.g. "+919876543210" or "SBIINB" */
  sender: string;
  /** Full message body */
  body: string;
  /** Device-reported timestamp */
  receivedAt: Date;
};

/**
 * Returns true when a message is worth uploading to the backend.
 *
 * Called entirely on-device; no network I/O.
 */
export function looksLikeFinancialAlert(msg: RawMessage): boolean {
  const { body } = msg;

  if (body.length < MIN_BODY_LENGTH) return false;
  if (OTP_RE.test(body)) return false;
  if (!FINANCIAL_RE.test(body)) return false;

  return true;
}

/** Apply the prefilter to an array and return the subset worth uploading. */
export function prefilterMessages(messages: RawMessage[]): RawMessage[] {
  return messages.filter(looksLikeFinancialAlert);
}

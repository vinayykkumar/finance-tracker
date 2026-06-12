/**
 * On-device prefilter: decide whether an SMS is worth sending to the sync
 * API at all. This is a coarse, documented heuristic — NOT the source of
 * truth for "is this a bank transaction" (that honest match/no-match call is
 * made server-side by app.modules.sms_messages.parsers; an included message
 * can still come back `parse_status: "unparsed"`).
 *
 * Two independent checks, both must hold:
 *
 * 1. The sender looks like a bank/DLT sender ID, not a personal contact —
 *    either a DLT header ("AD-HDFCBK", "VM-ICICIB") or a short all-caps
 *    alphanumeric code (4-16 chars, e.g. "HDFCBK"). Plain phone numbers
 *    (personal contacts, OTP-from-friends, etc.) never match.
 * 2. The body mentions money/transaction language (debited, credited, UPI,
 *    a currency amount, ...).
 *
 * On top of that, ANY message whose body looks like it carries a one-time
 * passcode, PIN, CVV, or password is EXCLUDED outright, even from a bank
 * sender that also matches (1) and (2) — those never leave the device.
 */

const SENSITIVE_RE =
  /\b(otp|one[- ]?time password|one[- ]?time pin|cvv|atm pin|\bpin\b|password|passcode|do not share|verification code)\b/i;

const BANK_SENDER_RE = /^[A-Z]{2}-[A-Z0-9]{3,}$|^[A-Z0-9]{4,16}$/;

const TRANSACTION_KEYWORDS_RE =
  /\b(debited|credited|debit|credit|spent|withdrawn|withdrawal|transferred|a\/c|acct|account|balance|upi|neft|imps|rtgs)\b/i;

const CURRENCY_AMOUNT_RE = /\b(rs\.?|inr)\s?\d/i;

export function looksLikeBankSender(sender: string): boolean {
  return BANK_SENDER_RE.test(sender.trim().toUpperCase());
}

export function looksLikeSensitive(body: string): boolean {
  return SENSITIVE_RE.test(body);
}

export function looksLikeTransaction(body: string): boolean {
  return TRANSACTION_KEYWORDS_RE.test(body) || CURRENCY_AMOUNT_RE.test(body);
}

/** Should this device SMS be included in a sync batch? */
export function shouldIncludeSms(msg: { address: string; body: string }): boolean {
  if (looksLikeSensitive(msg.body)) return false;
  return looksLikeBankSender(msg.address) && looksLikeTransaction(msg.body);
}

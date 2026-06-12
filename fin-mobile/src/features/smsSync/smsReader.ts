import { Platform } from "react-native";
import SmsAndroid from "react-native-get-sms-android";

import type { DeviceSmsMessage } from "./types";

export type ReadOptions = {
  /** Only return messages received at or after this device-clock epoch ms. */
  sinceMs: number;
  maxCount: number;
};

/**
 * Read recent inbox SMS within a bounded window.
 *
 * - Returns `[]` on every platform other than Android.
 * - Requires READ_SMS to already be granted — call
 *   `permissions.getSmsPermissionStatus()` first. If the permission is
 *   revoked between that check and this call (or the native module isn't
 *   linked, e.g. Expo Go), this rejects with a plain ``Error`` so the caller
 *   can show a clear "permission revoked" / "unavailable" message.
 */
export async function readInboxSms(opts: ReadOptions): Promise<DeviceSmsMessage[]> {
  if (Platform.OS !== "android") return [];

  // Bind to a const so TS narrows it to non-undefined inside the closure below.
  const sms = SmsAndroid;
  if (!sms) {
    throw new Error(
      "SMS reading is unavailable in this build. A development client with " +
        "react-native-get-sms-android linked is required (Expo Go cannot read SMS)."
    );
  }

  const filter = JSON.stringify({
    box: "inbox",
    minDate: opts.sinceMs,
    maxCount: opts.maxCount,
  });

  return new Promise((resolve, reject) => {
    sms.list(
      filter,
      (fail) => reject(new Error(fail || "Reading SMS failed (permission revoked?)")),
      (_count, smsList) => {
        try {
          const parsed = JSON.parse(smsList) as Array<{
            _id: number | string;
            address?: string;
            body?: string;
            date: number | string;
          }>;
          resolve(
            parsed.map((m) => ({
              id: String(m._id),
              address: m.address ?? "",
              body: m.body ?? "",
              date: Number(m.date),
            }))
          );
        } catch {
          reject(new Error("Failed to parse device SMS list"));
        }
      }
    );
  });
}

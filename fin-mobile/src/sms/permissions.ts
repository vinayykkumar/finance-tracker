/**
 * SMS permission helpers for Android.
 *
 * iOS is intentionally unsupported — Apple does not expose a public SMS-reading API.
 *
 * The READ_SMS permission is in Android's "dangerous" category and requires an
 * explicit user grant at runtime.  Google Play additionally requires a policy
 * declaration for apps using this permission (SMS / Call Log Default App policy).
 * See PRIVACY.md in the repository root for the full disclosure.
 */

import { PermissionsAndroid, Platform } from "react-native";

export type PermissionStatus = "granted" | "denied" | "blocked" | "unavailable";

/**
 * Show the system permission dialog and return the outcome.
 *
 * - "granted"     — user approved; SMS inbox is readable.
 * - "denied"      — user declined this time; can ask again.
 * - "blocked"     — user said "Never ask again"; must go to system settings.
 * - "unavailable" — running on iOS or a platform without READ_SMS.
 */
export async function requestSmsReadPermission(): Promise<PermissionStatus> {
  if (Platform.OS !== "android") return "unavailable";

  const result = await PermissionsAndroid.request(
    PermissionsAndroid.PERMISSIONS.READ_SMS,
    {
      title: "Bank SMS Sync",
      message:
        "Fin needs access to your SMS inbox to detect bank transaction alerts. " +
        "Only messages that look like financial alerts are analysed — " +
        "OTPs and personal texts are skipped locally and never sent to our servers. " +
        "Raw message text is never stored; only a hash and structured amounts are kept.",
      buttonNeutral: "Ask Me Later",
      buttonNegative: "Deny",
      buttonPositive: "Allow",
    }
  );

  if (result === PermissionsAndroid.RESULTS.GRANTED) return "granted";
  if (result === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) return "blocked";
  return "denied";
}

/** Returns true if READ_SMS is currently granted without showing a dialog. */
export async function checkSmsReadPermission(): Promise<boolean> {
  if (Platform.OS !== "android") return false;
  return PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.READ_SMS);
}

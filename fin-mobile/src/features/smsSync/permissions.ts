import { PermissionsAndroid, Platform } from "react-native";

import type { SmsPermissionStatus } from "./types";

/** Current READ_SMS permission state, without prompting. */
export async function getSmsPermissionStatus(): Promise<SmsPermissionStatus> {
  if (Platform.OS !== "android") return "unavailable";
  const granted = await PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.READ_SMS);
  return granted ? "granted" : "denied";
}

/**
 * Show the OS permission dialog. Callers should only invoke this after the
 * user has explicitly opted in via the in-app consent screen — Android's
 * dialog itself carries no context about *why* the app wants this.
 */
export async function requestSmsPermission(): Promise<SmsPermissionStatus> {
  if (Platform.OS !== "android") return "unavailable";
  const result = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.READ_SMS, {
    title: "Allow reading SMS messages?",
    message:
      "To detect bank and UPI transaction alerts, this app reads recent SMS messages from " +
      "senders that look like banks. Messages with OTPs, PINs, or passwords are never read " +
      "or sent. You can turn this off anytime in Settings.",
    buttonPositive: "Allow",
    buttonNegative: "Not now",
  });
  return result === PermissionsAndroid.RESULTS.GRANTED ? "granted" : "denied";
}

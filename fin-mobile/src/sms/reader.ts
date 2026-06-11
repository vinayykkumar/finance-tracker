/**
 * SMS inbox reader for Android.
 *
 * Production dependency: react-native-get-sms-android
 * ─────────────────────────────────────────────────────
 * This module requires ``react-native-get-sms-android`` which uses the
 * READ_SMS permission.  The app must be built as a development/production
 * build (not Expo Go) for native modules to load.
 *
 * Installation steps (already in package.json on this branch):
 *   npm install react-native-get-sms-android
 *
 * Android Manifest (handled by app.json plugin entry on this branch):
 *   <uses-permission android:name="android.permission.READ_SMS" />
 *
 * If the native module is absent (e.g. running in Expo Go), all calls return
 * an empty array rather than crashing.  A console warning is emitted.
 *
 * Google Play policy note
 * ─────────────────────────────────────────────────────
 * READ_SMS requires a Play Store policy declaration.  See PRIVACY.md.
 */

import { Platform } from "react-native";
import type { RawMessage } from "./prefilter";

export type ReadSmsOptions = {
  /** How many days back to look. Default: 30. */
  maxAgeDays?: number;
  /** Hard cap on messages returned. Default: 200. */
  maxCount?: number;
};

type SmsAndroidMessage = {
  _id: string;
  address: string;
  body: string;
  date: number;
};

/**
 * Read recent SMS messages from the device inbox.
 *
 * @returns Messages in unspecified order (callers should sort by receivedAt if needed).
 * @throws  Error if READ_SMS permission was not granted before calling.
 */
export async function readRecentSms(options: ReadSmsOptions = {}): Promise<RawMessage[]> {
  if (Platform.OS !== "android") {
    return [];
  }

  const { maxAgeDays = 30, maxCount = 200 } = options;
  const minDate = Date.now() - maxAgeDays * 24 * 60 * 60 * 1000;

  return new Promise<RawMessage[]>((resolve, reject) => {
    let SmsAndroid: { list: (filter: string, fail: (err: string) => void, success: (count: number, smsList: string) => void) => void } | null = null;
    try {
      // Dynamic require so this module tree-shakes out on iOS and doesn't
      // cause bundler errors when the package isn't installed.
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      SmsAndroid = require("react-native-get-sms-android").default;
    } catch {
      console.warn(
        "[sms/reader] react-native-get-sms-android not available. " +
          "Build with a development/production Expo build to enable SMS reading."
      );
      resolve([]);
      return;
    }

    if (!SmsAndroid) {
      resolve([]);
      return;
    }

    SmsAndroid.list(
      JSON.stringify({
        box: "inbox",
        minDate,
        maxDate: Date.now(),
        indexFrom: 0,
        maxCount,
      }),
      (fail: string) => reject(new Error(`SMS read failed: ${fail}`)),
      (_count: number, smsList: string) => {
        try {
          const msgs = JSON.parse(smsList) as SmsAndroidMessage[];
          resolve(
            msgs.map((m) => ({
              id: String(m._id),
              sender: m.address ?? "",
              body: m.body ?? "",
              receivedAt: new Date(m.date),
            }))
          );
        } catch (e) {
          reject(e);
        }
      }
    );
  });
}

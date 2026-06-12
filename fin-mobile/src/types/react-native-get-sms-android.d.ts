/**
 * react-native-get-sms-android ships no type declarations. This is a
 * minimal ambient typing for the one method this app uses
 * (see src/features/smsSync/smsReader.ts).
 *
 * On platforms/builds where the native module isn't linked (iOS, web,
 * Expo Go), `NativeModules.Sms` — and therefore this default export — is
 * `undefined` at runtime; smsReader.ts checks for that before calling
 * `.list`.
 */
declare module "react-native-get-sms-android" {
  export type SmsListFilter = {
    box: "inbox" | "sent" | "draft";
    /** Epoch milliseconds — only messages at/after this are returned. */
    minDate?: number;
    /** Epoch milliseconds — only messages at/before this are returned. */
    maxDate?: number;
    maxCount?: number;
  };

  export interface SmsAndroidModule {
    list(
      filter: string,
      fail: (error: string) => void,
      success: (count: number, smsList: string) => void
    ): void;
  }

  const SmsAndroid: SmsAndroidModule | undefined;
  export default SmsAndroid;
}

/**
 * Runtime config (Expo injects `EXPO_PUBLIC_*` at bundle time).
 * Android emulator: use `http://10.0.2.2:8000` to reach host machine's localhost.
 */
export function getApiBaseUrl(): string {
  const raw = process.env.EXPO_PUBLIC_API_BASE_URL ?? "";
  return String(raw).replace(/\/$/, "");
}

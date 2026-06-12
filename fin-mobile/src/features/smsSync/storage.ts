import AsyncStorage from "@react-native-async-storage/async-storage";

const KEY_ENABLED = "sms_sync.enabled";
const KEY_LAST_SYNCED_AT = "sms_sync.last_synced_at_ms";

/** Local opt-in flag — gates whether "Sync now" / auto-sync runs at all. */
export async function getSmsSyncEnabled(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEY_ENABLED)) === "true";
}

export async function setSmsSyncEnabled(enabled: boolean): Promise<void> {
  if (enabled) {
    await AsyncStorage.setItem(KEY_ENABLED, "true");
  } else {
    // Disabling clears local sync state too — re-enabling later starts a
    // fresh window rather than silently resuming from a stale cursor.
    await AsyncStorage.removeMany([KEY_ENABLED, KEY_LAST_SYNCED_AT]);
  }
}

export async function getLastSyncedAtMs(): Promise<number | null> {
  const raw = await AsyncStorage.getItem(KEY_LAST_SYNCED_AT);
  return raw ? Number(raw) : null;
}

export async function setLastSyncedAtMs(epochMs: number): Promise<void> {
  await AsyncStorage.setItem(KEY_LAST_SYNCED_AT, String(epochMs));
}

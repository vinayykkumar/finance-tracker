/**
 * Fraction of `available` consumed by `actual_spend`, clamped to [0, 100].
 *
 * Used to drive the per-category progress bar. If there's nothing available
 * (no cap, or a cap fully consumed by a previous overspend with no rollover),
 * any positive spend reads as fully "used" rather than dividing by zero/negative.
 */
export function progressValue(actualSpend: string, available: string | null): number {
  const spent = Number(actualSpend);
  const avail = available !== null ? Number(available) : 0;
  if (!Number.isFinite(spent)) return 0;
  if (!Number.isFinite(avail) || avail <= 0) return spent > 0 ? 100 : 0;
  return Math.min((spent / avail) * 100, 100);
}

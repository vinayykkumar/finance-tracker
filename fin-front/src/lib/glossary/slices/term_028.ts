/**
 * Glossary slice (028): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "028" as const;
export const termEn = "exchange rate" as const;
export function describeTerm(): string {
  return termEn;
}

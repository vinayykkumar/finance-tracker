/**
 * Glossary slice (035): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "035" as const;
export const termEn = "401k rollover" as const;
export function describeTerm(): string {
  return termEn;
}

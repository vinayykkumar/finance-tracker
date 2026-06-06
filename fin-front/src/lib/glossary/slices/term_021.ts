/**
 * Glossary slice (021): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "021" as const;
export const termEn = "debit card" as const;
export function describeTerm(): string {
  return termEn;
}

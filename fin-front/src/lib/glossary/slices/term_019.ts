/**
 * Glossary slice (019): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "019" as const;
export const termEn = "credit limit" as const;
export function describeTerm(): string {
  return termEn;
}

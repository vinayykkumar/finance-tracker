/**
 * Glossary slice (040): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "040" as const;
export const termEn = "income statement" as const;
export function describeTerm(): string {
  return termEn;
}

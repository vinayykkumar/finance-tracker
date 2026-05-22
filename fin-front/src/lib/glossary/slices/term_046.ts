/**
 * Glossary slice (046): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "046" as const;
export const termEn = "journal entry" as const;
export function describeTerm(): string {
  return termEn;
}

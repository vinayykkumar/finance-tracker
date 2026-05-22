/**
 * Glossary slice (038): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "038" as const;
export const termEn = "high yield savings" as const;
export function describeTerm(): string {
  return termEn;
}
